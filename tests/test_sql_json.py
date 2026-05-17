"""Tests para odev sql --json — salida JSON para agentes.

Cubre:
  - C6-1: rows returned as list-of-dicts
  - C6-2: empty result → []
  - C6-3: psql error → stderr JSON + exit 1
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import typer


def _make_contexto(tmp_path: Path) -> MagicMock:
    """Crea un ProjectContext mock con directorio temporal."""
    ctx = MagicMock()
    ctx.directorio_config = tmp_path
    ctx.nombre = "test-project"
    ctx.config = MagicMock()
    ctx.config.rutas_addons = None
    return ctx


def _call_run_sql_json(
    tmp_path: Path,
    mock_dc: MagicMock,
    query: str,
    env_valores: dict | None = None,
):
    """Llama _run_sql con json=True y contexto mockeado."""
    from odev.commands.sql import _run_sql

    ctx = _make_contexto(tmp_path)
    env = env_valores if env_valores is not None else {"DB_NAME": "odoo_db", "DB_USER": "odoo"}

    with (
        patch("odev.commands.sql.requerir_proyecto", return_value=ctx),
        patch("odev.commands.sql.obtener_docker", return_value=mock_dc),
        patch("odev.commands.sql.obtener_rutas") as mock_rutas,
        patch("odev.commands.sql.load_env", return_value=env),
        patch("odev.main.obtener_nombre_proyecto", return_value="test-project"),
    ):
        mock_rutas.return_value.env_file = tmp_path / ".env"
        try:
            _run_sql(query, csv=False, json_output=True)
        except (SystemExit, typer.Exit) as e:
            return e
    return None


# ---------------------------------------------------------------------------
# TestSqlJson (Spec C6-1 / C6-2 / C6-3)
# ---------------------------------------------------------------------------


class TestSqlJson:
    """Salida --json del comando sql."""

    def test_json_filas_como_lista_de_dicts(self, tmp_path: Path, capsys) -> None:
        """C6-1: rows returned as list-of-dicts con column names como keys."""
        mock_dc = MagicMock()
        # Simula salida de psql con ASCII Unit Separator (0x1f) como delimitador
        # Header line: col1\x1fcol2
        # Data lines: val1\x1fval2
        psql_output = b"id\x1fname\nrow1_id\x1fAlice\nrow2_id\x1fBob\n"
        mock_dc.exec_capture.return_value = (psql_output, b"", 0)

        _call_run_sql_json(tmp_path, mock_dc, "SELECT id, name FROM res_partner LIMIT 2")

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert isinstance(data, list)
        assert len(data) == 2
        assert "id" in data[0]
        assert "name" in data[0]

    def test_json_zero_rows(self, tmp_path: Path, capsys) -> None:
        """C6-2: zero rows → stdout es [] y exit 0."""
        mock_dc = MagicMock()
        # Solo header, sin filas de datos
        psql_output = b"id\x1fname\n"
        mock_dc.exec_capture.return_value = (psql_output, b"", 0)

        exc = _call_run_sql_json(tmp_path, mock_dc, "SELECT id, name FROM res_partner WHERE 1=0")

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data == []
        if exc is not None:
            code = exc.code if isinstance(exc, SystemExit) else exc.exit_code
            assert code == 0

    def test_json_psql_error_stderr_json_exit_1(self, tmp_path: Path, capsys) -> None:
        """C6-3: psql error → stderr JSON con key 'error' y exit 1."""
        mock_dc = MagicMock()
        mock_dc.exec_capture.return_value = (b"", b"ERROR: syntax error at or near \"INVALID\"", 1)

        exc = _call_run_sql_json(tmp_path, mock_dc, "INVALID SQL")

        assert exc is not None
        code = exc.code if isinstance(exc, SystemExit) else exc.exit_code
        assert code == 1
        captured = capsys.readouterr()
        err_data = json.loads(captured.err)
        assert "error" in err_data
