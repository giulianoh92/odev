"""RED tests for _execute_logs(contexto, service, tail) -> list[dict].

C6-R1: helper returns structured log entries without Typer side effects.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def _make_contexto() -> MagicMock:
    ctx = MagicMock()
    ctx.nombre = "test-project"
    ctx.config = MagicMock()
    ctx.config.rutas_addons = None
    return ctx


_RAW_LOGS = (
    "web  | 2024-01-01T00:00:00.000000000Z "
    "1 1 INFO odoo.http: Request\n"
    "web  | 2024-01-01T00:00:01.000000000Z "
    "2 2 ERROR odoo.models: Something failed\n"
)


class TestExecuteLogs:
    """_execute_logs returns structured log list, no stdout."""

    def test_happy_path_returns_list_of_dicts(self) -> None:
        """Returns [{service, timestamp, level, message}] for captured logs."""
        from odev.commands.logs import _execute_logs

        mock_dc = MagicMock()
        mock_dc.logs_capture.return_value = _RAW_LOGS

        ctx = _make_contexto()
        with patch("odev.commands.logs.obtener_docker", return_value=mock_dc):
            result = _execute_logs(ctx, "web", tail=100)

        assert isinstance(result, list)
        assert len(result) == 2
        for entry in result:
            assert "service" in entry
            assert "timestamp" in entry
            assert "level" in entry
            assert "message" in entry

    def test_empty_logs_returns_empty_list(self) -> None:
        """No logs → returns []."""
        from odev.commands.logs import _execute_logs

        mock_dc = MagicMock()
        mock_dc.logs_capture.return_value = ""

        ctx = _make_contexto()
        with patch("odev.commands.logs.obtener_docker", return_value=mock_dc):
            result = _execute_logs(ctx, "web", tail=100)

        assert result == []

    def test_no_stdout_side_effect(self, capsys) -> None:
        """_execute_logs must not write to stdout."""
        from odev.commands.logs import _execute_logs

        mock_dc = MagicMock()
        mock_dc.logs_capture.return_value = _RAW_LOGS

        ctx = _make_contexto()
        with patch("odev.commands.logs.obtener_docker", return_value=mock_dc):
            _execute_logs(ctx, "web", tail=100)

        captured = capsys.readouterr()
        assert captured.out == ""

    def test_no_typer_exit_raised(self) -> None:
        """_execute_logs does NOT raise typer.Exit on success."""
        import typer

        from odev.commands.logs import _execute_logs

        mock_dc = MagicMock()
        mock_dc.logs_capture.return_value = ""

        ctx = _make_contexto()
        raised = False
        try:
            with patch("odev.commands.logs.obtener_docker", return_value=mock_dc):
                _execute_logs(ctx, "web", tail=50)
        except typer.Exit:
            raised = True

        assert not raised, "_execute_logs must not raise typer.Exit"

    def test_calls_logs_capture_with_correct_args(self) -> None:
        """logs_capture is called with the correct service and tail args."""
        from odev.commands.logs import _execute_logs

        mock_dc = MagicMock()
        mock_dc.logs_capture.return_value = ""

        ctx = _make_contexto()
        with patch("odev.commands.logs.obtener_docker", return_value=mock_dc):
            _execute_logs(ctx, "db", tail=200)

        mock_dc.logs_capture.assert_called_once_with("db", tail=200)
