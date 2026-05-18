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
        with patch("odev.commands.model_info.obtener_docker", return_value=mock_dc):
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
        with patch("odev.commands.model_info.obtener_docker", return_value=mock_dc):
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
            with patch("odev.commands.model_info.obtener_docker", return_value=mock_dc):
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
        with patch("odev.commands.model_info.obtener_docker", return_value=mock_dc):
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
        with patch("odev.commands.model_info.obtener_docker", return_value=mock_dc):
            with pytest.raises((RuntimeError, ValueError, subprocess.CalledProcessError)):
                _execute_model_info(ctx, "res.partner")
