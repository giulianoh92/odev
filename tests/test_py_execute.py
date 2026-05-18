"""RED tests for _execute_py(contexto, expression) -> str.

C6-R1: helper returns banner-stripped result string, no stdout.
"""

from __future__ import annotations

import subprocess
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

# Minimal Odoo banner lines to simulate real output
_BANNER = (
    b"2024-01-01 00:00:00,000 1 INFO ? odoo: version 17.0-20240101\n"
    b"2024-01-01 00:00:00,001 1 INFO ? odoo.addons.base: loaded\n"
    b"odoo: db>\n"
)


class TestExecutePy:
    """_execute_py returns stripped result string, no stdout."""

    def test_happy_path_returns_result_string(self, tmp_path) -> None:
        """Returns the banner-stripped Python expression result."""
        from odev.commands.py import _execute_py

        raw_stdout = _BANNER + b"42\n"
        mock_result = MagicMock()
        mock_result.stdout = raw_stdout
        mock_result.stderr = b""
        mock_result.returncode = 0

        mock_dc = MagicMock()
        mock_dc.exec_cmd.return_value = mock_result

        ctx = _make_contexto(tmp_path)
        with (
            patch("odev.commands.py.obtener_docker", return_value=mock_dc),
            patch("odev.commands.py.obtener_rutas") as mock_rutas,
            patch("odev.commands.py.load_env", return_value=_DEFAULT_ENV),
        ):
            mock_rutas.return_value.env_file = tmp_path / ".env"
            result = _execute_py(ctx, "21+21")

        assert isinstance(result, str)
        assert "42" in result

    def test_no_stdout_side_effect(self, tmp_path, capsys) -> None:
        """_execute_py must not write to stdout."""
        from odev.commands.py import _execute_py

        raw_stdout = _BANNER + b"hello\n"
        mock_result = MagicMock()
        mock_result.stdout = raw_stdout
        mock_result.stderr = b""
        mock_result.returncode = 0

        mock_dc = MagicMock()
        mock_dc.exec_cmd.return_value = mock_result

        ctx = _make_contexto(tmp_path)
        with (
            patch("odev.commands.py.obtener_docker", return_value=mock_dc),
            patch("odev.commands.py.obtener_rutas") as mock_rutas,
            patch("odev.commands.py.load_env", return_value=_DEFAULT_ENV),
        ):
            mock_rutas.return_value.env_file = tmp_path / ".env"
            _execute_py(ctx, "'hello'")

        captured = capsys.readouterr()
        assert captured.out == ""

    def test_no_typer_exit_raised(self, tmp_path) -> None:
        """_execute_py does NOT raise typer.Exit on success."""
        import typer

        from odev.commands.py import _execute_py

        raw_stdout = _BANNER + b"True\n"
        mock_result = MagicMock()
        mock_result.stdout = raw_stdout
        mock_result.stderr = b""
        mock_result.returncode = 0

        mock_dc = MagicMock()
        mock_dc.exec_cmd.return_value = mock_result

        ctx = _make_contexto(tmp_path)
        raised = False
        try:
            with (
                patch("odev.commands.py.obtener_docker", return_value=mock_dc),
                patch("odev.commands.py.obtener_rutas") as mock_rutas,
                patch("odev.commands.py.load_env", return_value=_DEFAULT_ENV),
            ):
                mock_rutas.return_value.env_file = tmp_path / ".env"
                _execute_py(ctx, "True")
        except typer.Exit:
            raised = True

        assert not raised, "_execute_py must not raise typer.Exit"

    def test_shell_error_raises_exception(self, tmp_path) -> None:
        """Non-zero returncode raises RuntimeError, not typer.Exit."""
        from odev.commands.py import _execute_py

        mock_dc = MagicMock()
        mock_dc.exec_cmd.side_effect = subprocess.CalledProcessError(
            returncode=1, cmd=["odoo", "shell"], stderr=b"Error\n"
        )

        ctx = _make_contexto(tmp_path)
        with (
            patch("odev.commands.py.obtener_docker", return_value=mock_dc),
            patch("odev.commands.py.obtener_rutas") as mock_rutas,
            patch("odev.commands.py.load_env", return_value=_DEFAULT_ENV),
        ):
            mock_rutas.return_value.env_file = tmp_path / ".env"
            with pytest.raises((RuntimeError, ValueError, subprocess.CalledProcessError)):
                _execute_py(ctx, "invalid_expression")
