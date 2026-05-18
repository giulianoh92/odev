"""RED tests for _execute_doctor(contexto) -> dict.

C6-R1: helper returns doctor JSON schema dict without Typer side effects.
"""

from __future__ import annotations

from unittest.mock import MagicMock


def _make_contexto() -> MagicMock:
    ctx = MagicMock()
    ctx.nombre = "test-project"
    ctx.config = MagicMock()
    ctx.config.rutas_addons = None
    return ctx


class TestExecuteDoctor:
    """_execute_doctor returns full doctor JSON schema dict, no stdout."""

    def test_happy_path_returns_dict_with_required_keys(self) -> None:
        """Returns dict with version/checks/summary/exit_code keys."""
        from odev.commands.doctor import _execute_doctor

        ctx = _make_contexto()
        result = _execute_doctor(ctx)

        assert isinstance(result, dict)
        assert "version" in result
        assert "checks" in result
        assert "summary" in result
        assert "exit_code" in result

    def test_checks_is_list(self) -> None:
        """checks key contains a list of CheckResult dicts."""
        from odev.commands.doctor import _execute_doctor

        ctx = _make_contexto()
        result = _execute_doctor(ctx)

        assert isinstance(result["checks"], list)
        for check in result["checks"]:
            assert "name" in check
            assert "status" in check
            assert "message" in check

    def test_no_stdout_side_effect(self, capsys) -> None:
        """_execute_doctor must not write to stdout."""
        from odev.commands.doctor import _execute_doctor

        ctx = _make_contexto()
        _execute_doctor(ctx)

        captured = capsys.readouterr()
        assert captured.out == ""

    def test_no_typer_exit_raised(self) -> None:
        """_execute_doctor does NOT raise typer.Exit on success."""
        import typer

        from odev.commands.doctor import _execute_doctor

        ctx = _make_contexto()
        raised = False
        try:
            _execute_doctor(ctx)
        except typer.Exit:
            raised = True

        assert not raised, "_execute_doctor must not raise typer.Exit"

    def test_summary_has_ok_warn_fail_keys(self) -> None:
        """summary dict contains ok/warn/fail integer counters."""
        from odev.commands.doctor import _execute_doctor

        ctx = _make_contexto()
        result = _execute_doctor(ctx)

        summary = result["summary"]
        assert "ok" in summary
        assert "warn" in summary
        assert "fail" in summary
        assert isinstance(summary["ok"], int)
        assert isinstance(summary["warn"], int)
        assert isinstance(summary["fail"], int)
