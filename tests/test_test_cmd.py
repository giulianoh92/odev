"""Tests para el comando 'odev test' — modos de salida y flags.

Verifica el routing TTY/no-TTY, flags --summary/--failures/--json/--save-log,
propagacion del exit code, y manejo de Ctrl+C. Usa FakePopen para evitar
subprocesos reales. Llama _run_test() directamente para evitar problemas
con OptionInfo defaults de Typer al invocar test() fuera del CLI runner.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# FakePopen — simula subprocess.Popen sin lanzar procesos reales
# ---------------------------------------------------------------------------


class FakePopen:
    """Simula un subprocess.Popen con stdout pre-alimentado por fixture."""

    def __init__(self, output: str, returncode: int = 0) -> None:
        self.stdout = io.BytesIO(output.encode("utf-8"))
        self.returncode = returncode
        self._poll_count = 0

    def poll(self) -> int | None:
        """Retorna None la primera vez, luego el returncode."""
        if self._poll_count == 0:
            self._poll_count += 1
            return None
        return self.returncode

    def terminate(self) -> None:
        """No-op en tests."""

    def wait(self, timeout: float | None = None) -> int:
        return self.returncode

    def kill(self) -> None:
        """No-op en tests."""


# ---------------------------------------------------------------------------
# Fixtures de salida Odoo reutilizables
# ---------------------------------------------------------------------------

_FIXTURE_ALL_PASS = """\
2024-01-15 10:00:00,001 1234 INFO odoo.addons.sale.tests.test_sale_order TestSaleOrder.test_create: Finished
2024-01-15 10:00:00,200 1234 INFO odoo.addons.sale.tests.test_sale_order TestSaleOrder.test_cancel: Finished
Ran 2 tests in 0.200s

OK
"""

_FIXTURE_ONE_FAIL = """\
2024-01-15 10:00:01,000 1234 ERROR odoo.addons.sale.tests.test_sale_order FAIL: TestSaleOrder.test_create
Traceback (most recent call last):
  File "/odoo/addons/sale/tests/test_sale_order.py", line 42, in test_create
    self.assertEqual(order.state, "sale")
AssertionError: 'draft' != 'sale'
2024-01-15 10:00:01,200 1234 INFO odoo.addons.sale.tests.test_sale_order TestSaleOrder.test_cancel: Finished
Ran 2 tests in 1.200s

FAILED (failures=1)
"""

_FIXTURE_MALFORMED = """\
2024-01-15 10:00:00,001 1234 INFO odoo.modules.loading Loading module sale (1/42)
Process died unexpectedly
"""


# ---------------------------------------------------------------------------
# Helper: contexto mock y patches compartidos
# ---------------------------------------------------------------------------


def _make_contexto(tmp_path: Path) -> MagicMock:
    """Crea un ProjectContext mock con directorio temporal."""
    ctx = MagicMock()
    ctx.directorio_config = tmp_path
    ctx.nombre = "test-project"
    ctx.config = MagicMock()
    ctx.config.rutas_addons = None
    return ctx


def _default_run_kwargs() -> dict:
    """Kwargs base para _run_test en tests que no necesitan personalizar flags."""
    return {
        "module": "sale",
        "log_level": "test",
        "summary": False,
        "failures_only": False,
        "json_out": False,
        "tags": None,
        "save_log": None,
    }


def _call_run_test(tmp_path: Path, mock_dc: MagicMock, **overrides):
    """Llama _run_test con contexto mockeado y kwargs base + overrides."""
    from odev.commands.test import _run_test

    ctx = _make_contexto(tmp_path)
    kwargs = {**_default_run_kwargs(), **overrides}

    with (
        patch("odev.commands.test.requerir_proyecto", return_value=ctx),
        patch("odev.commands.test.obtener_rutas") as mock_rutas,
        patch("odev.commands.test.obtener_docker", return_value=mock_dc),
        patch("odev.commands.test.load_env", return_value={"DB_NAME": "test_db"}),
        patch("odev.main.obtener_nombre_proyecto", return_value="test-project"),
    ):
        mock_rutas.return_value.env_file = tmp_path / ".env"
        try:
            _run_test(**kwargs)
        except (SystemExit, Exception) as e:
            import typer

            if isinstance(e, (SystemExit, typer.Exit)):
                return e
            raise


# ---------------------------------------------------------------------------
# T1 — TTY=True, sin flags → exec_cmd con interactive=True
# ---------------------------------------------------------------------------


class TestTtyPathInteractive:
    """T1: stdout es TTY, sin flags → ruta legacy exec_cmd interactive."""

    def test_tty_sin_flags_llama_exec_cmd_interactivo(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """Con TTY activo y sin flags, se llama exec_cmd(interactive=True)."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: True)

        mock_dc = MagicMock()
        mock_dc.exec_cmd = MagicMock()
        mock_dc.exec_cmd_stream = MagicMock()

        _call_run_test(tmp_path, mock_dc)

        mock_dc.exec_cmd.assert_called_once()
        call_args = mock_dc.exec_cmd.call_args
        # interactive=True puede ser posicional (arg[2]) o keyword
        interactive_value = call_args[1].get("interactive") or (
            len(call_args[0]) > 2 and call_args[0][2]
        )
        assert interactive_value is True
        mock_dc.exec_cmd_stream.assert_not_called()

    def test_tty_sin_flags_no_llama_stream(self, tmp_path: Path, monkeypatch) -> None:
        """Con TTY activo, exec_cmd_stream NO es llamado."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: True)

        mock_dc = MagicMock()
        mock_dc.exec_cmd = MagicMock()
        mock_dc.exec_cmd_stream = MagicMock()

        _call_run_test(tmp_path, mock_dc)

        mock_dc.exec_cmd_stream.assert_not_called()


# ---------------------------------------------------------------------------
# T2 — TTY=False, sin flags → exec_cmd_stream + summary a stdout
# ---------------------------------------------------------------------------


class TestNoTtyAutoSummary:
    """T2: stdout no es TTY, sin flags → stream + auto-summary."""

    def test_no_tty_sin_flags_llama_stream(self, tmp_path: Path, monkeypatch) -> None:
        """Sin TTY, se llama exec_cmd_stream (no exec_cmd interactivo)."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)

        fake_popen = FakePopen(_FIXTURE_ALL_PASS, returncode=0)
        mock_dc = MagicMock()
        mock_dc.exec_cmd_stream.return_value = fake_popen

        _call_run_test(tmp_path, mock_dc)

        mock_dc.exec_cmd_stream.assert_called_once()

    def test_no_tty_sin_flags_imprime_resumen(
        self, tmp_path: Path, monkeypatch, capsys
    ) -> None:
        """Sin TTY, el comando imprime conteo de tests al stdout."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)

        fake_popen = FakePopen(_FIXTURE_ALL_PASS, returncode=0)
        mock_dc = MagicMock()
        mock_dc.exec_cmd_stream.return_value = fake_popen

        _call_run_test(tmp_path, mock_dc)

        captured = capsys.readouterr()
        # Summary debe contener conteo de tests (2) y/o keywords
        output = captured.out + captured.err
        assert "2" in output or "passed" in output.lower()


# ---------------------------------------------------------------------------
# T3 — --summary flag → resumen con duracion, sin raw log
# ---------------------------------------------------------------------------


class TestSummaryFlag:
    """T3: --summary imprime resumen con duracion."""

    def test_summary_flag_imprime_duracion(
        self, tmp_path: Path, monkeypatch, capsys
    ) -> None:
        """--summary imprime la duracion total del run."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)

        fake_popen = FakePopen(_FIXTURE_ALL_PASS, returncode=0)
        mock_dc = MagicMock()
        mock_dc.exec_cmd_stream.return_value = fake_popen

        _call_run_test(tmp_path, mock_dc, summary=True)

        captured = capsys.readouterr()
        output = captured.out + captured.err
        # Duration 0.200s o 0.2 debe aparecer, o el conteo de 2 tests
        assert "0.2" in output or "2" in output

    def test_summary_flag_suprime_log_crudo(
        self, tmp_path: Path, monkeypatch, capsys
    ) -> None:
        """--summary NO emite el log crudo de Odoo en stdout."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)

        fake_popen = FakePopen(_FIXTURE_ALL_PASS, returncode=0)
        mock_dc = MagicMock()
        mock_dc.exec_cmd_stream.return_value = fake_popen

        _call_run_test(tmp_path, mock_dc, summary=True)

        captured = capsys.readouterr()
        assert "odoo.addons.sale.tests" not in captured.out


# ---------------------------------------------------------------------------
# T4 — --failures, failures present → bloques FAIL/ERROR visibles
# ---------------------------------------------------------------------------


class TestFailuresFlag:
    """T4: --failures imprime solo bloques de fallos/errores."""

    def test_failures_flag_imprime_bloque_fail(
        self, tmp_path: Path, monkeypatch, capsys
    ) -> None:
        """--failures imprime clase.metodo del test fallido."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)

        fake_popen = FakePopen(_FIXTURE_ONE_FAIL, returncode=1)
        mock_dc = MagicMock()
        mock_dc.exec_cmd_stream.return_value = fake_popen

        _call_run_test(tmp_path, mock_dc, failures_only=True)

        captured = capsys.readouterr()
        output = captured.out + captured.err
        assert "TestSaleOrder" in output or "test_create" in output


# ---------------------------------------------------------------------------
# T5 — --failures, no failures → mensaje "all tests passed"
# ---------------------------------------------------------------------------


class TestFailuresFlagNone:
    """T5: --failures sin fallos → indicacion de todo OK."""

    def test_failures_flag_sin_fallos_indica_ok(
        self, tmp_path: Path, monkeypatch, capsys
    ) -> None:
        """--failures con run exitoso muestra indicacion de exito."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)

        fake_popen = FakePopen(_FIXTURE_ALL_PASS, returncode=0)
        mock_dc = MagicMock()
        mock_dc.exec_cmd_stream.return_value = fake_popen

        _call_run_test(tmp_path, mock_dc, failures_only=True)

        captured = capsys.readouterr()
        output = (captured.out + captured.err).lower()
        assert "passed" in output or "ok" in output or "exitoso" in output


# ---------------------------------------------------------------------------
# T6 — --json → stdout es JSON valido con campos requeridos
# ---------------------------------------------------------------------------


class TestJsonFlag:
    """T6: --json emite JSON valido sin decoraciones Rich."""

    def test_json_flag_emite_json_valido(
        self, tmp_path: Path, monkeypatch, capsys
    ) -> None:
        """--json produce stdout parseable como JSON con campos requeridos."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)

        fake_popen = FakePopen(_FIXTURE_ALL_PASS, returncode=0)
        mock_dc = MagicMock()
        mock_dc.exec_cmd_stream.return_value = fake_popen

        _call_run_test(tmp_path, mock_dc, json_out=True)

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "total" in data
        assert "passed" in data
        assert "failed" in data
        assert "errors" in data
        assert "failures" in data
        assert isinstance(data["failures"], list)

    def test_json_flag_sin_output_rich(
        self, tmp_path: Path, monkeypatch, capsys
    ) -> None:
        """--json no emite markup Rich en stdout."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)

        fake_popen = FakePopen(_FIXTURE_ALL_PASS, returncode=0)
        mock_dc = MagicMock()
        mock_dc.exec_cmd_stream.return_value = fake_popen

        _call_run_test(tmp_path, mock_dc, json_out=True)

        captured = capsys.readouterr()
        # Markup Rich usa "[bold" o "[green" — no debe aparecer en modo JSON
        assert "[bold" not in captured.out
        assert "[green" not in captured.out


# ---------------------------------------------------------------------------
# T7 — --save-log → archivo escrito con log crudo
# ---------------------------------------------------------------------------


class TestSaveLogFlag:
    """T7: --save-log guarda el log crudo en el archivo indicado."""

    def test_save_log_escribe_archivo(
        self, tmp_path: Path, monkeypatch, capsys
    ) -> None:
        """--save-log crea el archivo con el contenido del log Odoo."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)

        fake_popen = FakePopen(_FIXTURE_ALL_PASS, returncode=0)
        mock_dc = MagicMock()
        mock_dc.exec_cmd_stream.return_value = fake_popen

        log_file = tmp_path / "test.log"
        _call_run_test(tmp_path, mock_dc, save_log=log_file)

        assert log_file.exists()
        content = log_file.read_text()
        assert "Ran 2 tests" in content or "odoo.addons" in content

    def test_save_log_tambien_imprime_resumen(
        self, tmp_path: Path, monkeypatch, capsys
    ) -> None:
        """--save-log imprime resumen en stdout ademas de guardar el archivo."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)

        fake_popen = FakePopen(_FIXTURE_ALL_PASS, returncode=0)
        mock_dc = MagicMock()
        mock_dc.exec_cmd_stream.return_value = fake_popen

        log_file = tmp_path / "test2.log"
        _call_run_test(tmp_path, mock_dc, save_log=log_file)

        captured = capsys.readouterr()
        assert len(captured.out) > 0


# ---------------------------------------------------------------------------
# T8 — Exit code propagation
# ---------------------------------------------------------------------------


class TestExitCodePropagation:
    """T8: exit code del subproceso se propaga al caller."""

    def test_exit_code_uno_cuando_popen_falla(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """Popen.returncode=1 → typer.Exit(1) o SystemExit(1) lanzado."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)

        fake_popen = FakePopen(_FIXTURE_ONE_FAIL, returncode=1)
        mock_dc = MagicMock()
        mock_dc.exec_cmd_stream.return_value = fake_popen

        import typer

        from odev.commands.test import _run_test

        ctx = _make_contexto(tmp_path)
        with (
            patch("odev.commands.test.requerir_proyecto", return_value=ctx),
            patch("odev.commands.test.obtener_rutas") as mock_rutas,
            patch("odev.commands.test.obtener_docker", return_value=mock_dc),
            patch("odev.commands.test.load_env", return_value={"DB_NAME": "test_db"}),
            patch("odev.main.obtener_nombre_proyecto", return_value="test-project"),
        ):
            mock_rutas.return_value.env_file = tmp_path / ".env"
            with pytest.raises((SystemExit, typer.Exit)) as exc_info:
                _run_test(**{**_default_run_kwargs(), "module": "sale"})

        exc = exc_info.value
        code = exc.code if isinstance(exc, SystemExit) else exc.exit_code
        assert code == 1

    def test_exit_code_cero_cuando_popen_exitoso(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """Popen.returncode=0 → exit 0."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)

        fake_popen = FakePopen(_FIXTURE_ALL_PASS, returncode=0)
        mock_dc = MagicMock()
        mock_dc.exec_cmd_stream.return_value = fake_popen

        import typer

        from odev.commands.test import _run_test

        ctx = _make_contexto(tmp_path)
        with (
            patch("odev.commands.test.requerir_proyecto", return_value=ctx),
            patch("odev.commands.test.obtener_rutas") as mock_rutas,
            patch("odev.commands.test.obtener_docker", return_value=mock_dc),
            patch("odev.commands.test.load_env", return_value={"DB_NAME": "test_db"}),
            patch("odev.main.obtener_nombre_proyecto", return_value="test-project"),
        ):
            mock_rutas.return_value.env_file = tmp_path / ".env"
            try:
                _run_test(**{**_default_run_kwargs(), "module": "sale"})
            except (SystemExit, typer.Exit) as e:
                code = e.code if isinstance(e, SystemExit) else e.exit_code
                assert code == 0


# ---------------------------------------------------------------------------
# T9 — D1: --json + --failures composable
# ---------------------------------------------------------------------------


class TestJsonFailuresComposable:
    """T9 (D1): --json + --failures producen JSON filtrado con solo fallos."""

    def test_json_failures_composable_con_fallos(
        self, tmp_path: Path, monkeypatch, capsys
    ) -> None:
        """--json --failures emite JSON con failures array no vacio cuando hay fallos."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)

        fake_popen = FakePopen(_FIXTURE_ONE_FAIL, returncode=1)
        mock_dc = MagicMock()
        mock_dc.exec_cmd_stream.return_value = fake_popen

        _call_run_test(tmp_path, mock_dc, json_out=True, failures_only=True)

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        # Debe ser JSON valido con failures array no vacio
        assert "failures" in data
        assert isinstance(data["failures"], list)
        assert len(data["failures"]) == 1

    def test_json_failures_vacio_cuando_todos_pasan(
        self, tmp_path: Path, monkeypatch, capsys
    ) -> None:
        """--json --failures con run exitoso: JSON con failures[] vacio."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)

        fake_popen = FakePopen(_FIXTURE_ALL_PASS, returncode=0)
        mock_dc = MagicMock()
        mock_dc.exec_cmd_stream.return_value = fake_popen

        _call_run_test(tmp_path, mock_dc, json_out=True, failures_only=True)

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["failures"] == []
