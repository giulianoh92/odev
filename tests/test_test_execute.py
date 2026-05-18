"""RED tests for _execute_test(contexto, module, tags=None) -> dict.

C6-R1: helper returns TestResult dict without Typer side effects.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def _make_contexto(tmp_path) -> MagicMock:
    ctx = MagicMock()
    ctx.directorio_config = tmp_path
    ctx.nombre = "test-project"
    ctx.config = MagicMock()
    ctx.config.rutas_addons = None
    return ctx


_DEFAULT_ENV = {"DB_NAME": "odoo_db", "DB_USER": "odoo"}

# Minimal Odoo test output that produces a parseable TestResult
_TEST_OUTPUT_OK = [
    "Ran 1 test in 0.123s\n",
    "OK\n",
]

_TEST_OUTPUT_FAIL = [
    "FAIL: TestMyModule.test_something\n",
    "Ran 1 test in 0.456s\n",
    "FAILED (failures=1)\n",
]


def _make_popen_mock(lines, returncode=0):
    """Create a mock Popen with iterable stdout."""
    mock_popen = MagicMock()
    mock_popen.stdout = [line.encode() for line in lines]
    mock_popen.returncode = returncode
    mock_popen.wait.return_value = returncode
    return mock_popen


class TestExecuteTest:
    """_execute_test returns TestResult dict, no stdout."""

    def test_happy_path_returns_dict_with_required_keys(self, tmp_path) -> None:
        """Returns dict with total/passed/failed/errors/duration keys."""
        from odev.commands.test import _execute_test

        mock_popen = _make_popen_mock(_TEST_OUTPUT_OK, returncode=0)
        mock_dc = MagicMock()
        mock_dc.exec_cmd_stream.return_value = mock_popen

        ctx = _make_contexto(tmp_path)
        with (
            patch("odev.commands.test.obtener_docker", return_value=mock_dc),
            patch("odev.commands.test.obtener_rutas") as mock_rutas,
            patch("odev.commands.test.load_env", return_value=_DEFAULT_ENV),
            patch("odev.commands.test.validar_modulos"),
        ):
            mock_rutas.return_value.env_file = tmp_path / ".env"
            result = _execute_test(ctx, "my_module")

        assert isinstance(result, dict)
        for key in ("total", "passed", "failed", "errors", "duration"):
            assert key in result, f"Expected key '{key}' in result"

    def test_no_stdout_side_effect(self, tmp_path, capsys) -> None:
        """_execute_test must not write to stdout."""
        from odev.commands.test import _execute_test

        mock_popen = _make_popen_mock(_TEST_OUTPUT_OK, returncode=0)
        mock_dc = MagicMock()
        mock_dc.exec_cmd_stream.return_value = mock_popen

        ctx = _make_contexto(tmp_path)
        with (
            patch("odev.commands.test.obtener_docker", return_value=mock_dc),
            patch("odev.commands.test.obtener_rutas") as mock_rutas,
            patch("odev.commands.test.load_env", return_value=_DEFAULT_ENV),
            patch("odev.commands.test.validar_modulos"),
        ):
            mock_rutas.return_value.env_file = tmp_path / ".env"
            _execute_test(ctx, "my_module")

        captured = capsys.readouterr()
        assert captured.out == ""

    def test_no_typer_exit_raised(self, tmp_path) -> None:
        """_execute_test does NOT raise typer.Exit on success."""
        import typer

        from odev.commands.test import _execute_test

        mock_popen = _make_popen_mock(_TEST_OUTPUT_OK, returncode=0)
        mock_dc = MagicMock()
        mock_dc.exec_cmd_stream.return_value = mock_popen

        ctx = _make_contexto(tmp_path)
        raised = False
        try:
            with (
                patch("odev.commands.test.obtener_docker", return_value=mock_dc),
                patch("odev.commands.test.obtener_rutas") as mock_rutas,
                patch("odev.commands.test.load_env", return_value=_DEFAULT_ENV),
                patch("odev.commands.test.validar_modulos"),
            ):
                mock_rutas.return_value.env_file = tmp_path / ".env"
                _execute_test(ctx, "my_module")
        except typer.Exit:
            raised = True

        assert not raised, "_execute_test must not raise typer.Exit"

    def test_with_tags_passes_tags_to_result(self, tmp_path) -> None:
        """Tags parameter is accepted without error."""
        from odev.commands.test import _execute_test

        mock_popen = _make_popen_mock(_TEST_OUTPUT_OK, returncode=0)
        mock_dc = MagicMock()
        mock_dc.exec_cmd_stream.return_value = mock_popen

        ctx = _make_contexto(tmp_path)
        with (
            patch("odev.commands.test.obtener_docker", return_value=mock_dc),
            patch("odev.commands.test.obtener_rutas") as mock_rutas,
            patch("odev.commands.test.load_env", return_value=_DEFAULT_ENV),
            patch("odev.commands.test.validar_modulos"),
        ):
            mock_rutas.return_value.env_file = tmp_path / ".env"
            result = _execute_test(ctx, "my_module", tags="/my_module:MyClass")

        assert isinstance(result, dict)
