"""RED tests for _execute_sql(contexto, query) -> list[dict].

C6-R1: helper returns data without Typer side effects.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def _make_contexto(tmp_path) -> MagicMock:
    ctx = MagicMock()
    ctx.directorio_config = tmp_path
    ctx.nombre = "test-project"
    ctx.config = MagicMock()
    ctx.config.rutas_addons = None
    return ctx


_DEFAULT_ENV = {"DB_NAME": "odoo_db", "DB_USER": "odoo"}


class TestExecuteSql:
    """_execute_sql returns structured data, no stdout."""

    def test_happy_path_returns_list_of_dicts(self, tmp_path) -> None:
        """Returns list of row dicts for a valid query."""
        from odev.commands.sql import _execute_sql

        # Build raw bytes that _parse_psql_us_output expects
        # header + data row, separated by \x1f
        raw = b"id\x1fname\n1\x1fAlice\n2\x1fBob\n"
        mock_dc = MagicMock()
        mock_dc.exec_capture.return_value = (raw, b"", 0)

        ctx = _make_contexto(tmp_path)
        with (
            patch("odev.commands.sql.obtener_docker", return_value=mock_dc),
            patch("odev.commands.sql.obtener_rutas") as mock_rutas,
            patch("odev.commands.sql.load_env", return_value=_DEFAULT_ENV),
        ):
            mock_rutas.return_value.env_file = tmp_path / ".env"
            result = _execute_sql(ctx, "SELECT id, name FROM res_partner")

        assert isinstance(result, list)
        assert len(result) == 2
        for row in result:
            assert "id" in row
            assert "name" in row

    def test_empty_result_returns_empty_list(self, tmp_path) -> None:
        """No rows → returns []."""
        from odev.commands.sql import _execute_sql

        mock_dc = MagicMock()
        mock_dc.exec_capture.return_value = (b"", b"", 0)

        ctx = _make_contexto(tmp_path)
        with (
            patch("odev.commands.sql.obtener_docker", return_value=mock_dc),
            patch("odev.commands.sql.obtener_rutas") as mock_rutas,
            patch("odev.commands.sql.load_env", return_value=_DEFAULT_ENV),
        ):
            mock_rutas.return_value.env_file = tmp_path / ".env"
            result = _execute_sql(ctx, "SELECT 1 WHERE 1=2")

        assert result == []

    def test_no_stdout_side_effect(self, tmp_path, capsys) -> None:
        """_execute_sql must not write to stdout."""
        from odev.commands.sql import _execute_sql

        mock_dc = MagicMock()
        mock_dc.exec_capture.return_value = (b"col\nval\n", b"", 0)

        ctx = _make_contexto(tmp_path)
        with (
            patch("odev.commands.sql.obtener_docker", return_value=mock_dc),
            patch("odev.commands.sql.obtener_rutas") as mock_rutas,
            patch("odev.commands.sql.load_env", return_value=_DEFAULT_ENV),
        ):
            mock_rutas.return_value.env_file = tmp_path / ".env"
            _execute_sql(ctx, "SELECT 1")

        captured = capsys.readouterr()
        assert captured.out == ""

    def test_no_typer_exit_raised(self, tmp_path) -> None:
        """_execute_sql does NOT raise typer.Exit on success."""
        import typer

        from odev.commands.sql import _execute_sql

        mock_dc = MagicMock()
        mock_dc.exec_capture.return_value = (b"", b"", 0)

        ctx = _make_contexto(tmp_path)
        raised = False
        try:
            with (
                patch("odev.commands.sql.obtener_docker", return_value=mock_dc),
                patch("odev.commands.sql.obtener_rutas") as mock_rutas,
                patch("odev.commands.sql.load_env", return_value=_DEFAULT_ENV),
            ):
                mock_rutas.return_value.env_file = tmp_path / ".env"
                _execute_sql(ctx, "SELECT 1")
        except typer.Exit:
            raised = True

        assert not raised, "_execute_sql must not raise typer.Exit"

    def test_psql_error_raises_runtime_error(self, tmp_path) -> None:
        """psql non-zero returncode raises RuntimeError, not typer.Exit."""
        from odev.commands.sql import _execute_sql

        mock_dc = MagicMock()
        mock_dc.exec_capture.return_value = (b"", b"ERROR: syntax error\n", 1)

        ctx = _make_contexto(tmp_path)
        with (
            patch("odev.commands.sql.obtener_docker", return_value=mock_dc),
            patch("odev.commands.sql.obtener_rutas") as mock_rutas,
            patch("odev.commands.sql.load_env", return_value=_DEFAULT_ENV),
        ):
            mock_rutas.return_value.env_file = tmp_path / ".env"
            with pytest.raises((RuntimeError, ValueError)):
                _execute_sql(ctx, "INVALID SQL")
