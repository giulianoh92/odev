"""Tests para odev modules — listado de modulos instalados.

Cubre:
  - C9-1: JSON array con name, state, version (--json/-j)
  - C9-2: no modules → []
  - C9-3: no project context → exit 1
  - D1: tabla Rich human-readable por default, JSON solo con --json/-j
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import typer


def _make_contexto(tmp_path: Path) -> MagicMock:
    """Crea un ProjectContext mock con directorio temporal."""
    ctx = MagicMock()
    ctx.directorio_config = tmp_path
    ctx.nombre = "test-project"
    ctx.config = MagicMock()
    ctx.config.rutas_addons = None
    return ctx


def _call_modules(
    tmp_path: Path,
    mock_dc: MagicMock,
    env_valores: dict | None = None,
    json_output: bool = True,
):
    """Llama modules() con contexto mockeado."""
    from odev.commands.modules import modules

    ctx = _make_contexto(tmp_path)
    env = env_valores if env_valores is not None else {"DB_NAME": "odoo_db", "DB_USER": "odoo"}

    with (
        patch("odev.commands.modules.requerir_proyecto", return_value=ctx),
        patch("odev.commands.modules.obtener_docker", return_value=mock_dc),
        patch("odev.commands.modules.obtener_rutas") as mock_rutas,
        patch("odev.commands.modules.load_env", return_value=env),
        patch("odev.main.obtener_nombre_proyecto", return_value="test-project"),
    ):
        mock_rutas.return_value.env_file = tmp_path / ".env"
        try:
            modules(json_output=json_output)
        except (SystemExit, typer.Exit) as e:
            return e
    return None


# ---------------------------------------------------------------------------
# TestModulesJson (Spec C9-1 / C9-2 / C9-3)
# ---------------------------------------------------------------------------


class TestModulesJson:
    """Comando odev modules --json."""

    def test_json_lista_de_modulos_instalados(self, tmp_path: Path, capsys) -> None:
        """C9-1: stdout es JSON array con name, state, version."""
        mock_dc = MagicMock()
        # psql output con ASCII US delimiter (0x1f): name\x1fstate\x1fversion
        psql_out = b"sale\x1finstalled\x1f17.0.1.0.0\nstock\x1finstalled\x1f17.0.2.0.0\n"
        mock_dc.exec_capture.return_value = (psql_out, b"", 0)

        _call_modules(tmp_path, mock_dc)

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert isinstance(data, list)
        assert len(data) == 2
        for item in data:
            assert "name" in item
            assert "state" in item
            assert "version" in item

    def test_json_sin_modulos_lista_vacia(self, tmp_path: Path, capsys) -> None:
        """C9-2: sin modulos instalados → stdout es [] y exit 0."""
        mock_dc = MagicMock()
        mock_dc.exec_capture.return_value = (b"", b"", 0)

        exc = _call_modules(tmp_path, mock_dc)

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data == []
        if exc is not None:
            code = exc.code if isinstance(exc, SystemExit) else exc.exit_code
            assert code == 0

    def test_sin_proyecto_exit_1(self, tmp_path: Path, capsys) -> None:
        """C9-3: sin proyecto → exit 1, stdout limpio, diagnostico JSON por stderr."""
        from odev.core.resolver import ProyectoNoEncontradoError

        with (
            patch(
                "odev.commands.modules.requerir_proyecto",
                side_effect=ProyectoNoEncontradoError("no project"),
            ),
            patch("odev.main.obtener_nombre_proyecto", return_value=None),
        ):
            exc = None
            try:
                from odev.commands.modules import modules
                modules(json_output=True)
            except (SystemExit, typer.Exit) as e:
                exc = e

        assert exc is not None
        code = exc.code if isinstance(exc, SystemExit) else exc.exit_code
        assert code == 1

        captured = capsys.readouterr()
        assert captured.out == "", f"stdout no esta limpio: {captured.out!r}"
        data = json.loads(captured.err)
        assert "no project" in data["error"]


class TestModulesTableDefault:
    """D1: 'odev modules' sin flags muestra una tabla Rich, no JSON."""

    def test_sin_flags_no_emite_json_en_stdout(self, tmp_path: Path, capsys) -> None:
        """Bare 'odev modules' (json_output=False) no debe emitir un JSON array."""
        mock_dc = MagicMock()
        psql_out = b"sale\x1finstalled\x1f17.0.1.0.0\nstock\x1finstalled\x1f17.0.2.0.0\n"
        mock_dc.exec_capture.return_value = (psql_out, b"", 0)

        _call_modules(tmp_path, mock_dc, json_output=False)

        captured = capsys.readouterr()
        with pytest.raises(json.JSONDecodeError):
            json.loads(captured.out)

    def test_sin_flags_tabla_incluye_nombres_de_modulo(self, tmp_path: Path, capsys) -> None:
        """La tabla human-readable debe listar los nombres de los modulos."""
        mock_dc = MagicMock()
        psql_out = b"sale\x1finstalled\x1f17.0.1.0.0\nstock\x1finstalled\x1f17.0.2.0.0\n"
        mock_dc.exec_capture.return_value = (psql_out, b"", 0)

        _call_modules(tmp_path, mock_dc, json_output=False)

        captured = capsys.readouterr()
        assert "sale" in captured.out
        assert "stock" in captured.out

    def test_sin_flags_sin_modulos_no_crashea(self, tmp_path: Path, capsys) -> None:
        """Sin modulos instalados y sin --json, no debe lanzar excepcion ni imprimir []."""
        mock_dc = MagicMock()
        mock_dc.exec_capture.return_value = (b"", b"", 0)

        exc = _call_modules(tmp_path, mock_dc, json_output=False)

        captured = capsys.readouterr()
        assert exc is None
        assert "[]" not in captured.out

    def test_json_true_sigue_emitiendo_json(self, tmp_path: Path, capsys) -> None:
        """Con --json/-j explicito, el comportamiento JSON previo se mantiene intacto."""
        mock_dc = MagicMock()
        psql_out = b"sale\x1finstalled\x1f17.0.1.0.0\n"
        mock_dc.exec_capture.return_value = (psql_out, b"", 0)

        _call_modules(tmp_path, mock_dc, json_output=True)

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert isinstance(data, list)
        assert data[0]["name"] == "sale"
