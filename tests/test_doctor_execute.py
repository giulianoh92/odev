"""Tests para _execute_doctor(contexto) -> dict.

C6-R1: helper retorna el esquema JSON de doctor sin efectos secundarios de Typer.
Tras el refactor 0.6.0: _execute_doctor pasa contexto a los helpers.
Se usa contexto=None para degradacion graceful (todos los checks de proyecto retornan INFO).
"""

from __future__ import annotations


class TestExecuteDoctor:
    """_execute_doctor returns full doctor JSON schema dict, no stdout."""

    def test_happy_path_returns_dict_with_required_keys(self) -> None:
        """Returns dict with version/checks/summary/exit_code keys."""
        from odev.commands.doctor import _execute_doctor

        result = _execute_doctor(None)

        assert isinstance(result, dict)
        assert "version" in result
        assert "checks" in result
        assert "summary" in result
        assert "exit_code" in result

    def test_checks_is_list(self) -> None:
        """checks key contains a list of CheckResult dicts."""
        from odev.commands.doctor import _execute_doctor

        result = _execute_doctor(None)

        assert isinstance(result["checks"], list)
        for check in result["checks"]:
            assert "name" in check
            assert "status" in check
            assert "message" in check

    def test_no_stdout_side_effect(self, capsys) -> None:
        """_execute_doctor must not write to stdout."""
        from odev.commands.doctor import _execute_doctor

        _execute_doctor(None)

        captured = capsys.readouterr()
        assert captured.out == ""

    def test_no_typer_exit_raised(self) -> None:
        """_execute_doctor does NOT raise typer.Exit on success."""
        import typer

        from odev.commands.doctor import _execute_doctor

        raised = False
        try:
            _execute_doctor(None)
        except typer.Exit:
            raised = True

        assert not raised, "_execute_doctor must not raise typer.Exit"

    def test_summary_has_ok_warn_fail_keys(self) -> None:
        """summary dict contains ok/warn/fail integer counters."""
        from odev.commands.doctor import _execute_doctor

        result = _execute_doctor(None)

        summary = result["summary"]
        assert "ok" in summary
        assert "warn" in summary
        assert "fail" in summary
        assert isinstance(summary["ok"], int)
        assert isinstance(summary["warn"], int)
        assert isinstance(summary["fail"], int)
