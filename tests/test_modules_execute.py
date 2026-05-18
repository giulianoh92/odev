"""RED tests for _execute_modules(contexto) -> list[dict].

C6-R1: helper returns structured module list without Typer side effects.
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

# Psql output with \x1f separator: name\x1fstate\x1fversion
_RAW_MODULES = b"sale\x1finstalled\x1f16.0.1.0.0\nbase\x1finstalled\x1f16.0.1.0.0\n"


class TestExecuteModules:
    """_execute_modules returns structured module list, no stdout."""

    def test_happy_path_returns_list_of_dicts(self, tmp_path) -> None:
        """Returns [{name, state, version}] for installed modules."""
        from odev.commands.modules import _execute_modules

        mock_dc = MagicMock()
        mock_dc.exec_capture.return_value = (_RAW_MODULES, b"", 0)

        ctx = _make_contexto(tmp_path)
        with (
            patch("odev.commands.modules.obtener_docker", return_value=mock_dc),
            patch("odev.commands.modules.obtener_rutas") as mock_rutas,
            patch("odev.commands.modules.load_env", return_value=_DEFAULT_ENV),
        ):
            mock_rutas.return_value.env_file = tmp_path / ".env"
            result = _execute_modules(ctx)

        assert isinstance(result, list)
        assert len(result) == 2
        for mod in result:
            assert "name" in mod
            assert "state" in mod
            assert "version" in mod

    def test_empty_result_returns_empty_list(self, tmp_path) -> None:
        """No modules → returns []."""
        from odev.commands.modules import _execute_modules

        mock_dc = MagicMock()
        mock_dc.exec_capture.return_value = (b"", b"", 0)

        ctx = _make_contexto(tmp_path)
        with (
            patch("odev.commands.modules.obtener_docker", return_value=mock_dc),
            patch("odev.commands.modules.obtener_rutas") as mock_rutas,
            patch("odev.commands.modules.load_env", return_value=_DEFAULT_ENV),
        ):
            mock_rutas.return_value.env_file = tmp_path / ".env"
            result = _execute_modules(ctx)

        assert result == []

    def test_no_stdout_side_effect(self, tmp_path, capsys) -> None:
        """_execute_modules must not write to stdout."""
        from odev.commands.modules import _execute_modules

        mock_dc = MagicMock()
        mock_dc.exec_capture.return_value = (_RAW_MODULES, b"", 0)

        ctx = _make_contexto(tmp_path)
        with (
            patch("odev.commands.modules.obtener_docker", return_value=mock_dc),
            patch("odev.commands.modules.obtener_rutas") as mock_rutas,
            patch("odev.commands.modules.load_env", return_value=_DEFAULT_ENV),
        ):
            mock_rutas.return_value.env_file = tmp_path / ".env"
            _execute_modules(ctx)

        captured = capsys.readouterr()
        assert captured.out == ""

    def test_no_typer_exit_raised(self, tmp_path) -> None:
        """_execute_modules does NOT raise typer.Exit on success."""
        import typer

        from odev.commands.modules import _execute_modules

        mock_dc = MagicMock()
        mock_dc.exec_capture.return_value = (b"", b"", 0)

        ctx = _make_contexto(tmp_path)
        raised = False
        try:
            with (
                patch("odev.commands.modules.obtener_docker", return_value=mock_dc),
                patch("odev.commands.modules.obtener_rutas") as mock_rutas,
                patch("odev.commands.modules.load_env", return_value=_DEFAULT_ENV),
            ):
                mock_rutas.return_value.env_file = tmp_path / ".env"
                _execute_modules(ctx)
        except typer.Exit:
            raised = True

        assert not raised, "_execute_modules must not raise typer.Exit"

    def test_psql_error_raises_runtime_error(self, tmp_path) -> None:
        """psql non-zero returncode raises RuntimeError, not typer.Exit."""
        from odev.commands.modules import _execute_modules

        mock_dc = MagicMock()
        mock_dc.exec_capture.return_value = (b"", b"ERROR: connection refused\n", 1)

        ctx = _make_contexto(tmp_path)
        with (
            patch("odev.commands.modules.obtener_docker", return_value=mock_dc),
            patch("odev.commands.modules.obtener_rutas") as mock_rutas,
            patch("odev.commands.modules.load_env", return_value=_DEFAULT_ENV),
        ):
            mock_rutas.return_value.env_file = tmp_path / ".env"
            with pytest.raises((RuntimeError, ValueError)):
                _execute_modules(ctx)
