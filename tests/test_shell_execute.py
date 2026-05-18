"""RED tests for _execute_shell(contexto, service, command) -> dict.

C6-R1: helper returns {stdout, stderr, returncode} without Typer side effects.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def _make_contexto() -> MagicMock:
    ctx = MagicMock()
    ctx.nombre = "test-project"
    ctx.config = MagicMock()
    ctx.config.rutas_addons = None
    return ctx


class TestExecuteShell:
    """_execute_shell returns {stdout, stderr, returncode}, no stdout."""

    def test_happy_path_returns_dict_with_required_keys(self) -> None:
        """Returns dict with stdout/stderr/returncode keys."""
        from odev.commands.shell import _execute_shell

        mock_result = MagicMock()
        mock_result.stdout = b"hello world\n"
        mock_result.stderr = b""
        mock_result.returncode = 0

        mock_dc = MagicMock()
        mock_dc.exec_capture.return_value = (b"hello world\n", b"", 0)

        ctx = _make_contexto()
        with patch("odev.commands.shell.obtener_docker", return_value=mock_dc):
            result = _execute_shell(ctx, "web", "echo hello world")

        assert isinstance(result, dict)
        assert "stdout" in result
        assert "stderr" in result
        assert "returncode" in result

    def test_stdout_contains_command_output(self) -> None:
        """stdout key contains the decoded output."""
        from odev.commands.shell import _execute_shell

        mock_dc = MagicMock()
        mock_dc.exec_capture.return_value = (b"hello world\n", b"", 0)

        ctx = _make_contexto()
        with patch("odev.commands.shell.obtener_docker", return_value=mock_dc):
            result = _execute_shell(ctx, "web", "echo hello world")

        assert "hello world" in result["stdout"]

    def test_no_stdout_side_effect(self, capsys) -> None:
        """_execute_shell must not write to stdout."""
        from odev.commands.shell import _execute_shell

        mock_dc = MagicMock()
        mock_dc.exec_capture.return_value = (b"output\n", b"", 0)

        ctx = _make_contexto()
        with patch("odev.commands.shell.obtener_docker", return_value=mock_dc):
            _execute_shell(ctx, "web", "ls /")

        captured = capsys.readouterr()
        assert captured.out == ""

    def test_no_typer_exit_raised(self) -> None:
        """_execute_shell does NOT raise typer.Exit on success."""
        import typer

        from odev.commands.shell import _execute_shell

        mock_dc = MagicMock()
        mock_dc.exec_capture.return_value = (b"ok\n", b"", 0)

        ctx = _make_contexto()
        raised = False
        try:
            with patch("odev.commands.shell.obtener_docker", return_value=mock_dc):
                _execute_shell(ctx, "web", "echo ok")
        except typer.Exit:
            raised = True

        assert not raised, "_execute_shell must not raise typer.Exit"

    def test_nonzero_returncode_included_in_result(self) -> None:
        """Non-zero returncode is included in result dict (not raised as exit)."""
        from odev.commands.shell import _execute_shell

        mock_dc = MagicMock()
        mock_dc.exec_capture.return_value = (b"", b"error msg\n", 1)

        ctx = _make_contexto()
        with patch("odev.commands.shell.obtener_docker", return_value=mock_dc):
            result = _execute_shell(ctx, "web", "false")

        assert result["returncode"] == 1

    def test_calls_exec_capture_with_bash_c(self) -> None:
        """exec_capture is called with ['bash', '-c', command]."""
        from odev.commands.shell import _execute_shell

        mock_dc = MagicMock()
        mock_dc.exec_capture.return_value = (b"", b"", 0)

        ctx = _make_contexto()
        with patch("odev.commands.shell.obtener_docker", return_value=mock_dc):
            _execute_shell(ctx, "web", "ls /tmp")

        mock_dc.exec_capture.assert_called_once_with("web", ["bash", "-c", "ls /tmp"])
