"""RED tests for _execute_context(contexto) -> str.

C6-R1: helper returns markdown string without Typer side effects.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch


def _make_contexto(tmp_path: Path) -> MagicMock:
    ctx = MagicMock()
    ctx.nombre = "test-project"
    ctx.config = MagicMock()
    ctx.config.rutas_addons = None
    ctx.directorio_config = tmp_path
    return ctx


_DEFAULT_ENV = {
    "ODOO_VERSION": "17.0",
    "DB_NAME": "odoo_db",
    "DB_HOST": "db",
    "DB_PORT": "5432",
}


class TestExecuteContext:
    """_execute_context returns markdown string, no stdout."""

    def test_happy_path_returns_string(self, tmp_path: Path) -> None:
        """Returns a non-empty string."""
        from odev.commands.context import _execute_context

        ctx = _make_contexto(tmp_path)
        with (
            patch("odev.commands.context.obtener_rutas") as mock_rutas,
            patch("odev.commands.context.load_env", return_value=_DEFAULT_ENV),
        ):
            mock_rutas.return_value.env_file = tmp_path / ".env"
            mock_rutas.return_value.addons_dirs = []
            mock_rutas.return_value.root = tmp_path
            result = _execute_context(ctx)

        assert isinstance(result, str)
        assert len(result) > 0

    def test_no_stdout_side_effect(self, tmp_path: Path, capsys) -> None:
        """_execute_context must not write to stdout."""
        from odev.commands.context import _execute_context

        ctx = _make_contexto(tmp_path)
        with (
            patch("odev.commands.context.obtener_rutas") as mock_rutas,
            patch("odev.commands.context.load_env", return_value=_DEFAULT_ENV),
        ):
            mock_rutas.return_value.env_file = tmp_path / ".env"
            mock_rutas.return_value.addons_dirs = []
            mock_rutas.return_value.root = tmp_path
            _execute_context(ctx)

        captured = capsys.readouterr()
        assert captured.out == ""

    def test_no_typer_exit_raised(self, tmp_path: Path) -> None:
        """_execute_context does NOT raise typer.Exit on success."""
        import typer

        from odev.commands.context import _execute_context

        ctx = _make_contexto(tmp_path)
        raised = False
        try:
            with (
                patch("odev.commands.context.obtener_rutas") as mock_rutas,
                patch("odev.commands.context.load_env", return_value=_DEFAULT_ENV),
            ):
                mock_rutas.return_value.env_file = tmp_path / ".env"
                mock_rutas.return_value.addons_dirs = []
                mock_rutas.return_value.root = tmp_path
                _execute_context(ctx)
        except typer.Exit:
            raised = True

        assert not raised, "_execute_context must not raise typer.Exit"

    def test_result_contains_odoo_version(self, tmp_path: Path) -> None:
        """Returned string contains the Odoo version from env."""
        from odev.commands.context import _execute_context

        ctx = _make_contexto(tmp_path)
        with (
            patch("odev.commands.context.obtener_rutas") as mock_rutas,
            patch("odev.commands.context.load_env", return_value=_DEFAULT_ENV),
        ):
            mock_rutas.return_value.env_file = tmp_path / ".env"
            mock_rutas.return_value.addons_dirs = []
            mock_rutas.return_value.root = tmp_path
            result = _execute_context(ctx)

        assert "17.0" in result
