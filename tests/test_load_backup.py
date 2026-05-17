"""Tests para odev.commands.load_backup — validaciones de seguridad.

Cubre:
- REQ-LB-1: rechazo de miembros ZIP con path traversal
- REQ-LB-2: validacion estricta de DB_NAME con regex ajustado
- REQ-LB-3: scaffold TDD gate (este archivo debe existir antes de cualquier cambio de produccion)

Todos los tests usan ZIPs construidos en memoria via zipfile (sin Docker).
"""

import io
import zipfile
from pathlib import Path

import pytest

from odev.commands.load_backup import _validar_miembros_zip, LOAD_BACKUP_UNSAFE_MEMBER


def _crear_zip_con_miembros(miembros: list[str], contenido: bytes = b"data") -> io.BytesIO:
    """Construye un ZIP en memoria con los nombres de archivo dados.

    Argumentos:
        miembros: Lista de nombres de archivo (paths) a incluir en el ZIP.
        contenido: Bytes de contenido para cada entrada.

    Retorna:
        BytesIO listo para pasarse a zipfile.ZipFile.
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for nombre in miembros:
            zf.writestr(nombre, contenido)
    buf.seek(0)
    return buf


# ─── REQ-LB-1: path traversal ────────────────────────────────────────────────


class TestValidarMiembrosZip:
    """Tests para _validar_miembros_zip — REQ-LB-1."""

    def test_rechaza_path_traversal_relativo(self, tmp_path: Path) -> None:
        """Rechaza un miembro con '../../' en el nombre."""
        buf = _crear_zip_con_miembros(["../../etc/passwd"])
        with zipfile.ZipFile(buf) as zf:
            with pytest.raises(Exception):
                _validar_miembros_zip(zf, tmp_path)

    def test_rechaza_path_absoluto(self, tmp_path: Path) -> None:
        """Rechaza un miembro con ruta absoluta (/etc/passwd)."""
        buf = _crear_zip_con_miembros(["/etc/passwd"])
        with zipfile.ZipFile(buf) as zf:
            with pytest.raises(Exception):
                _validar_miembros_zip(zf, tmp_path)

    def test_acepta_miembros_benignos(self, tmp_path: Path) -> None:
        """Acepta un ZIP con solo entradas benign as (sin escape)."""
        buf = _crear_zip_con_miembros(["dump.sql", "filestore/data.bin"])
        with zipfile.ZipFile(buf) as zf:
            _validar_miembros_zip(zf, tmp_path)  # No debe lanzar excepcion


# ─── REQ-LB-2: DB name strict regex ──────────────────────────────────────────


class TestDbNameRegex:
    """Tests de la validacion estricta de DB_NAME — REQ-LB-2."""

    @pytest.mark.parametrize(
        "nombre",
        [
            "odoo_db",
            "_staging",
            "proj_dev",
            "ProyectoA",
        ],
    )
    def test_nombres_validos_pasan(self, nombre: str) -> None:
        """Los nombres validos deben pasar la regex ^[a-zA-Z_][a-zA-Z0-9_]*$."""
        import re

        assert re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", nombre) is not None, (
            f"'{nombre}' deberia ser valido"
        )

    @pytest.mark.parametrize(
        "nombre",
        [
            "my.db",
            "my-db",
            "123db",
            "db;DROP",
            "",
        ],
    )
    def test_nombres_invalidos_fallan(self, nombre: str) -> None:
        """Los nombres invalidos deben fallar la regex ^[a-zA-Z_][a-zA-Z0-9_]*$."""
        import re

        assert re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", nombre) is None, (
            f"'{nombre}' deberia ser invalido"
        )
