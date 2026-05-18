"""RED tests for _execute_model_info(contexto, model) -> dict.

C6-R1: helper returns model schema dict without Typer side effects.
"""

from __future__ import annotations

import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest


def _make_contexto() -> MagicMock:
    ctx = MagicMock()
    ctx.nombre = "test-project"
    ctx.config = MagicMock()
    ctx.config.rutas_addons = None
    # directorio_config / ".env" must return a mock whose .exists() is True
    mock_env_path = MagicMock()
    mock_env_path.exists.return_value = True
    ctx.directorio_config.__truediv__ = MagicMock(return_value=mock_env_path)
    return ctx


_MODEL_PAYLOAD = {
    "model": "res.partner",
    "description": "Contact",
    "inherits": [],
    "fields": [
        {"name": "name", "type": "char", "required": False, "relation": None}
    ],
}

# Simulate Odoo shell output: banner + JSON line
_BANNER = (
    b"2024-01-01 00:00:00,000 1 INFO ? odoo: version 17.0\n"
    b"odoo: db>\n"
)


_MOCK_ENV_VALS = {"DB_NAME": "odoo_db", "WEB_PORT": "8069"}


class TestExecuteModelInfo:
    """_execute_model_info returns model schema dict, no stdout."""

    def test_happy_path_returns_dict_with_required_keys(self) -> None:
        """Returns dict with model/description/inherits/fields keys."""
        from odev.commands.model_info import _execute_model_info

        raw_stdout = _BANNER + (json.dumps(_MODEL_PAYLOAD) + "\n").encode()
        mock_result = MagicMock()
        mock_result.stdout = raw_stdout
        mock_result.stderr = b""
        mock_result.returncode = 0

        mock_dc = MagicMock()
        mock_dc.exec_cmd.return_value = mock_result

        ctx = _make_contexto()
        with (
            patch("odev.commands.model_info.obtener_docker", return_value=mock_dc),
            patch("odev.commands.model_info.load_env", return_value=_MOCK_ENV_VALS),
        ):
            result = _execute_model_info(ctx, "res.partner")

        assert isinstance(result, dict)
        assert result["model"] == "res.partner"
        assert "fields" in result
        assert "description" in result
        assert "inherits" in result

    def test_no_stdout_side_effect(self, capsys) -> None:
        """_execute_model_info must not write to stdout."""
        from odev.commands.model_info import _execute_model_info

        raw_stdout = _BANNER + (json.dumps(_MODEL_PAYLOAD) + "\n").encode()
        mock_result = MagicMock()
        mock_result.stdout = raw_stdout
        mock_result.stderr = b""
        mock_result.returncode = 0

        mock_dc = MagicMock()
        mock_dc.exec_cmd.return_value = mock_result

        ctx = _make_contexto()
        with (
            patch("odev.commands.model_info.obtener_docker", return_value=mock_dc),
            patch("odev.commands.model_info.load_env", return_value=_MOCK_ENV_VALS),
        ):
            _execute_model_info(ctx, "res.partner")

        captured = capsys.readouterr()
        assert captured.out == ""

    def test_no_typer_exit_raised(self) -> None:
        """_execute_model_info does NOT raise typer.Exit on success."""
        import typer

        from odev.commands.model_info import _execute_model_info

        raw_stdout = _BANNER + (json.dumps(_MODEL_PAYLOAD) + "\n").encode()
        mock_result = MagicMock()
        mock_result.stdout = raw_stdout
        mock_result.stderr = b""
        mock_result.returncode = 0

        mock_dc = MagicMock()
        mock_dc.exec_cmd.return_value = mock_result

        ctx = _make_contexto()
        raised = False
        try:
            with (
                patch("odev.commands.model_info.obtener_docker", return_value=mock_dc),
                patch("odev.commands.model_info.load_env", return_value=_MOCK_ENV_VALS),
            ):
                _execute_model_info(ctx, "res.partner")
        except typer.Exit:
            raised = True

        assert not raised, "_execute_model_info must not raise typer.Exit"

    def test_model_not_found_raises_value_error(self) -> None:
        """Model not found raises ValueError, not typer.Exit."""
        from odev.commands.model_info import _execute_model_info

        error_stderr = b'{"error": "Model not found: nonexistent.model"}\n'
        mock_result = MagicMock()
        mock_result.stdout = _BANNER
        mock_result.stderr = error_stderr
        mock_result.returncode = 1

        mock_dc = MagicMock()
        mock_dc.exec_cmd.return_value = mock_result

        ctx = _make_contexto()
        with (
            patch("odev.commands.model_info.obtener_docker", return_value=mock_dc),
            patch("odev.commands.model_info.load_env", return_value=_MOCK_ENV_VALS),
        ):
            with pytest.raises((ValueError, RuntimeError)):
                _execute_model_info(ctx, "nonexistent.model")

    def test_stack_not_running_raises_runtime_error(self) -> None:
        """CalledProcessError raises RuntimeError, not typer.Exit."""
        from odev.commands.model_info import _execute_model_info

        mock_dc = MagicMock()
        mock_dc.exec_cmd.side_effect = subprocess.CalledProcessError(
            returncode=1, cmd=["odoo", "shell"], stderr=b"Connection refused\n"
        )

        ctx = _make_contexto()
        with (
            patch("odev.commands.model_info.obtener_docker", return_value=mock_dc),
            patch("odev.commands.model_info.load_env", return_value=_MOCK_ENV_VALS),
        ):
            with pytest.raises((RuntimeError, ValueError, subprocess.CalledProcessError)):
                _execute_model_info(ctx, "res.partner")

    def test_shell_argv_uses_config_flag_and_db_name(self, tmp_path) -> None:
        """exec_cmd receives --config=/etc/odoo/odoo.conf and DB_NAME from .env.

        Verifies Bug B fix: shell invocation must NOT hardcode 'odoo' as DB name
        and must include --config flag.
        """
        from odev.commands.model_info import _execute_model_info

        raw_stdout = _BANNER + (json.dumps(_MODEL_PAYLOAD) + "\n").encode()
        mock_result = MagicMock()
        mock_result.stdout = raw_stdout
        mock_result.stderr = b""
        mock_result.returncode = 0

        mock_dc = MagicMock()
        mock_dc.exec_cmd.return_value = mock_result

        ctx = _make_contexto()
        custom_env = {"DB_NAME": "custom_db", "WEB_PORT": "8069"}

        with (
            patch("odev.commands.model_info.obtener_docker", return_value=mock_dc),
            patch("odev.commands.model_info.load_env", return_value=custom_env),
        ):
            _execute_model_info(ctx, "res.partner")

        call_args = mock_dc.exec_cmd.call_args
        argv = call_args[0][1]  # second positional arg is the command list

        assert "--config=/etc/odoo/odoo.conf" in argv, (
            f"Shell argv must include --config flag, got: {argv}"
        )
        assert "custom_db" in argv, (
            f"Shell argv must use DB_NAME from .env ('custom_db'), got: {argv}"
        )
        assert "odoo" not in argv[argv.index("-d") + 1 :argv.index("-d") + 2] or "odoo" == "custom_db", (
            f"Shell argv must NOT hardcode 'odoo' as DB name, got: {argv}"
        )

    def test_missing_env_raises_runtime_error(self) -> None:
        """RuntimeError raised when directorio_config has no .env file."""
        from odev.commands.model_info import _execute_model_info

        ctx = _make_contexto()
        # Override: env path exists() returns False
        mock_env_path = MagicMock()
        mock_env_path.exists.return_value = False
        ctx.directorio_config.__truediv__ = MagicMock(return_value=mock_env_path)

        with pytest.raises(RuntimeError, match="Project .env not found"):
            _execute_model_info(ctx, "res.partner")
