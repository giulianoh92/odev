"""RED tests for _execute_status(contexto) -> list[dict].

C6-R1: helper returns data without Typer side effects.
"""

from __future__ import annotations

from unittest.mock import MagicMock


def _make_contexto() -> MagicMock:
    ctx = MagicMock()
    ctx.nombre = "test-project"
    ctx.modo = MagicMock()
    ctx.modo.value = "standard"
    ctx.config = MagicMock()
    ctx.config.rutas_addons = None
    return ctx


class TestExecuteStatus:
    """_execute_status returns structured list, no stdout."""

    def test_happy_path_returns_list_of_dicts(self, capsys) -> None:
        """Returns [{service, status, ports}] for running stack."""
        from odev.commands.status import _execute_status

        servicios = [
            {
                "Service": "web",
                "State": "running",
                "Publishers": [{"PublishedPort": 8069, "TargetPort": 8069}],
            },
            {"Service": "db", "State": "running", "Publishers": []},
        ]
        mock_dc = MagicMock()
        mock_dc.ps_parsed.return_value = servicios

        from unittest.mock import patch

        ctx = _make_contexto()
        with patch("odev.commands.status.obtener_docker", return_value=mock_dc):
            result = _execute_status(ctx)

        assert isinstance(result, list)
        assert len(result) == 2
        for item in result:
            assert "service" in item
            assert "status" in item
            assert "ports" in item

    def test_empty_stack_returns_empty_list(self, capsys) -> None:
        """Empty docker stack → returns []."""
        from odev.commands.status import _execute_status

        mock_dc = MagicMock()
        mock_dc.ps_parsed.return_value = []

        from unittest.mock import patch

        ctx = _make_contexto()
        with patch("odev.commands.status.obtener_docker", return_value=mock_dc):
            result = _execute_status(ctx)

        assert result == []

    def test_no_stdout_side_effect(self, capsys) -> None:
        """_execute_status must not write to stdout."""
        from odev.commands.status import _execute_status

        mock_dc = MagicMock()
        mock_dc.ps_parsed.return_value = []

        from unittest.mock import patch

        ctx = _make_contexto()
        with patch("odev.commands.status.obtener_docker", return_value=mock_dc):
            _execute_status(ctx)

        captured = capsys.readouterr()
        assert captured.out == ""

    def test_no_typer_exit_on_success(self) -> None:
        """_execute_status must NOT raise typer.Exit on normal success (aliased check)."""
        import typer

        from odev.commands.status import _execute_status

        mock_dc = MagicMock()
        mock_dc.ps_parsed.return_value = [
            {"Service": "web", "State": "running", "Publishers": []}
        ]

        from unittest.mock import patch

        ctx = _make_contexto()
        raised = False
        try:
            with patch("odev.commands.status.obtener_docker", return_value=mock_dc):
                _execute_status(ctx)
        except typer.Exit:
            raised = True

        assert not raised, "_execute_status must not raise typer.Exit"

    def test_no_typer_exit_raised(self) -> None:
        """_execute_status does NOT raise typer.Exit (clean check)."""
        import typer

        from odev.commands.status import _execute_status

        mock_dc = MagicMock()
        mock_dc.ps_parsed.return_value = []

        from unittest.mock import patch

        ctx = _make_contexto()
        raised = False
        try:
            with patch("odev.commands.status.obtener_docker", return_value=mock_dc):
                _execute_status(ctx)
        except typer.Exit:
            raised = True

        assert not raised, "_execute_status must not raise typer.Exit"

    def test_ports_extracted_correctly(self) -> None:
        """Published ports are extracted into list[int]."""
        from odev.commands.status import _execute_status

        servicios = [
            {
                "Service": "web",
                "State": "running",
                "Publishers": [
                    {"PublishedPort": 8069, "TargetPort": 8069},
                    {"PublishedPort": 5678, "TargetPort": 5678},
                ],
            }
        ]
        mock_dc = MagicMock()
        mock_dc.ps_parsed.return_value = servicios

        from unittest.mock import patch

        ctx = _make_contexto()
        with patch("odev.commands.status.obtener_docker", return_value=mock_dc):
            result = _execute_status(ctx)

        assert result[0]["ports"] == [8069, 5678]
