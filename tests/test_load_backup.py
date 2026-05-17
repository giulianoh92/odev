"""Tests para odev.commands.load_backup — validaciones de seguridad.

Cubre:
- REQ-LB-1: rechazo de miembros ZIP con path traversal
- REQ-LB-2: validacion estricta de DB_NAME con regex ajustado
- REQ-LB-3: scaffold TDD gate (este archivo debe existir antes de cualquier cambio de produccion)
- B3: streaming via exec_cmd_file (sin read_bytes en memoria)
- Q5: --dry-run preview sin ejecutar Docker

Todos los tests usan ZIPs construidos en memoria via zipfile (sin Docker).
"""

import io
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

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


# ─── B3: streaming via exec_cmd_file ─────────────────────────────────────────


def _crear_zip_backup(tmp_path: Path, nombre_dump: str = "dump.sql") -> Path:
    """Crea un ZIP de backup valido en disco con un dump dentro."""
    zip_path = tmp_path / "backup.zip"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(nombre_dump, b"-- SQL dump content")
    zip_path.write_bytes(buf.getvalue())
    return zip_path


def _hacer_mocks_base(tmp_path: Path):
    """Construye los mocks comunes para contexto, rutas y docker."""
    ctx = MagicMock()
    ctx.nombre = "test-project"

    env_file = tmp_path / ".env"
    env_file.write_text("DB_USER=odoo\nDB_NAME=odoo_db\nWEB_PORT=8069\n")

    rutas = MagicMock()
    rutas.env_file = env_file

    dc = MagicMock()
    dc.is_service_running.return_value = True
    dc.exec_cmd.return_value = MagicMock(returncode=0, stdout=b"")
    dc.exec_cmd_file.return_value = MagicMock(returncode=0, stdout=b"", stderr=b"")

    return ctx, rutas, dc


class TestLoadBackupStreaming:
    """B3 — verifica que load_backup usa exec_cmd_file en vez de read_bytes."""

    def test_usa_exec_cmd_file_para_dump_sql(self, tmp_path: Path) -> None:
        """Para dump.sql, load_backup llama exec_cmd_file (NO exec_cmd con stdin_data)."""
        zip_path = _crear_zip_backup(tmp_path, "dump.sql")
        ctx, rutas, dc = _hacer_mocks_base(tmp_path)

        with (
            patch("odev.commands.load_backup.requerir_proyecto", return_value=ctx),
            patch("odev.commands.load_backup.obtener_rutas", return_value=rutas),
            patch("odev.commands.load_backup.obtener_docker", return_value=dc),
            patch("odev.main.obtener_nombre_proyecto", return_value="test-project"),
            patch("odev.commands.load_backup.neutralizar_base_datos"),
            patch("odev.commands.load_backup.resetear_credenciales_admin"),
            patch("odev.commands.load_backup.configurar_parametros_desarrollo"),
        ):
            from odev.commands.load_backup import load_backup

            load_backup(backup=zip_path, neutralize=False, yes=True, dry_run=False)

        # exec_cmd_file debe haber sido llamado para el restore
        assert dc.exec_cmd_file.called, "exec_cmd_file no fue llamado"

        # El path pasado debe ser un Path apuntando al dump extraido
        call_args = dc.exec_cmd_file.call_args
        stdin_file_arg = call_args[1]["stdin_file"] if "stdin_file" in call_args[1] else call_args[0][2]
        assert isinstance(stdin_file_arg, Path)
        assert stdin_file_arg.name == "dump.sql"

    def test_dump_sql_path_pasado_a_exec_cmd_file(self, tmp_path: Path) -> None:
        """El path del dump SQL se pasa como stdin_file a exec_cmd_file."""
        zip_path = _crear_zip_backup(tmp_path, "dump.sql")
        ctx, rutas, dc = _hacer_mocks_base(tmp_path)

        with (
            patch("odev.commands.load_backup.requerir_proyecto", return_value=ctx),
            patch("odev.commands.load_backup.obtener_rutas", return_value=rutas),
            patch("odev.commands.load_backup.obtener_docker", return_value=dc),
            patch("odev.main.obtener_nombre_proyecto", return_value="test-project"),
            patch("odev.commands.load_backup.neutralizar_base_datos"),
            patch("odev.commands.load_backup.resetear_credenciales_admin"),
            patch("odev.commands.load_backup.configurar_parametros_desarrollo"),
        ):
            from odev.commands.load_backup import load_backup

            load_backup(backup=zip_path, neutralize=False, yes=True, dry_run=False)

        # exec_cmd_file debe haber sido llamado exactamente una vez para el restore
        assert dc.exec_cmd_file.call_count == 1

        # El comando pasado debe incluir psql
        call_args = dc.exec_cmd_file.call_args
        cmd_arg = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("command", [])
        assert "psql" in cmd_arg


# ─── Q5: --dry-run ────────────────────────────────────────────────────────────


class TestLoadBackupDryRun:
    """Q5 — verifica que --dry-run valida el ZIP pero no restaura."""

    def test_dry_run_valida_zip_pero_no_restaura(self, tmp_path: Path) -> None:
        """Con --dry-run: ZIP se valida, exec_cmd_file y exec_cmd NOT called."""
        zip_path = _crear_zip_backup(tmp_path, "dump.sql")
        ctx, rutas, dc = _hacer_mocks_base(tmp_path)

        with (
            patch("odev.commands.load_backup.requerir_proyecto", return_value=ctx),
            patch("odev.commands.load_backup.obtener_rutas", return_value=rutas),
            patch("odev.commands.load_backup.obtener_docker", return_value=dc),
            patch("odev.main.obtener_nombre_proyecto", return_value="test-project"),
        ):
            from odev.commands.load_backup import load_backup

            load_backup(backup=zip_path, neutralize=False, yes=True, dry_run=True)

        # exec_cmd_file NO debe ser llamado (no se restaura)
        dc.exec_cmd_file.assert_not_called()

        # exec_cmd NO debe ser llamado (sin dropdb, createdb, psql)
        dc.exec_cmd.assert_not_called()

    def test_dry_run_muestra_preview(self, tmp_path: Path, capsys) -> None:
        """Con --dry-run: la salida menciona el dump y la base de datos."""
        zip_path = _crear_zip_backup(tmp_path, "dump.sql")
        ctx, rutas, dc = _hacer_mocks_base(tmp_path)

        with (
            patch("odev.commands.load_backup.requerir_proyecto", return_value=ctx),
            patch("odev.commands.load_backup.obtener_rutas", return_value=rutas),
            patch("odev.commands.load_backup.obtener_docker", return_value=dc),
            patch("odev.main.obtener_nombre_proyecto", return_value="test-project"),
            patch("odev.commands.load_backup.info") as mock_info,
        ):
            from odev.commands.load_backup import load_backup

            load_backup(backup=zip_path, neutralize=False, yes=True, dry_run=True)

        # Algun info() menciona dump.sql o odoo_db
        all_msgs = " ".join(str(call) for call in mock_info.call_args_list)
        assert "dump.sql" in all_msgs or "odoo_db" in all_msgs
