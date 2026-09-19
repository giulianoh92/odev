"""Tests para el comando 'odev test' — modos de salida y flags.

Verifica el routing TTY/no-TTY, flags --summary/--failures/--json/--save-log,
propagacion del exit code, manejo de Ctrl+C, pre-flights de modulo/puerto y
merge de --tags. Usa FakePopen para evitar subprocesos reales.
Llama _run_test() directamente para evitar problemas con OptionInfo defaults
de Typer al invocar test() fuera del CLI runner.
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

# Fixture Odoo v19 para tests de nuevos campos JSON
_FIXTURE_V19_CLEAN = """\
2025-01-10 09:00:01,000 1234 INFO odoo.addons.my_module.tests.test_basic TestFlow.test_create: Finished
2025-01-10 09:00:01,400 1234 INFO odoo.tests.stats odoo.tests.stats: my_module: 4 tests 0.12s 8 queries
0 failed, 0 error(s) of 4 tests when loading database 'test_db'
"""

# Fixture con "Address already in use" y sin resumen parseble (port conflict)
_FIXTURE_PORT_CONFLICT = """\
2025-01-10 09:00:00,001 1234 INFO odoo.server Starting Odoo HTTP service
2025-01-10 09:00:00,100 1234 ERROR werkzeug Address already in use
Port 8069 is in use by another program.
"""

# Fixture con un test en ERROR (excepcion no capturada, no assertion failure)
_FIXTURE_ONE_ERROR = """\
2024-01-15 10:00:01,000 1234 ERROR odoo.addons.sale.tests.test_sale_order ERROR: TestSaleOrder.test_boom
Traceback (most recent call last):
  File "/odoo/addons/sale/tests/test_sale_order.py", line 55, in test_boom
    order.explode()
ValueError: boom
2024-01-15 10:00:01,200 1234 INFO odoo.addons.sale.tests.test_sale_order TestSaleOrder.test_cancel: Finished
Ran 2 tests in 1.200s

FAILED (errors=1)
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
    """Llama _run_test con contexto mockeado y kwargs base + overrides.

    Parches incluidos por defecto (no-op):
      - validar_modulo_existe: retorna None (bypass pre-flight de modulo)
    Los tests especificos de otras rutas deben pasar overrides
    usando patch.object o desactivando los mocks en su propio contexto.
    """
    from odev.commands.test import _run_test

    ctx = _make_contexto(tmp_path)
    kwargs = {**_default_run_kwargs(), **overrides}

    with (
        patch("odev.commands.test.requerir_proyecto", return_value=ctx),
        patch("odev.commands.test.obtener_rutas") as mock_rutas,
        patch("odev.commands.test.obtener_docker", return_value=mock_dc),
        patch("odev.commands.test.load_env", return_value={"DB_NAME": "test_db"}),
        patch("odev.main.obtener_nombre_proyecto", return_value="test-project"),
        patch("odev.commands.test.validar_modulo_existe", return_value=None),
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
# T1 — TTY=True, sin flags → summary compacto default (0.7.0)
# ---------------------------------------------------------------------------


class TestTtyCompactDefault:
    """T1 (0.7.0): stdout es TTY, sin flags → summary compacto, NO stream crudo.

    Antes de 0.7.0 el TTY sin flags usaba exec_cmd(interactive=True) con el
    log crudo de Odoo. Ahora el summary compacto es el default SIEMPRE;
    el stream crudo requiere --verbose explicito.
    """

    def test_tty_sin_flags_renderiza_summary(
        self, tmp_path: Path, monkeypatch, capsys
    ) -> None:
        """Con TTY activo y sin flags, se imprime el resumen compacto."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: True)

        fake_popen = FakePopen(_FIXTURE_ALL_PASS, returncode=0)
        mock_dc = MagicMock()
        mock_dc.exec_cmd_stream.return_value = fake_popen

        _call_run_test(tmp_path, mock_dc)

        mock_dc.exec_cmd_stream.assert_called_once()
        captured = capsys.readouterr()
        output = (captured.out + captured.err).lower()
        assert "passed" in output

    def test_tty_sin_flags_no_emite_log_crudo(
        self, tmp_path: Path, monkeypatch, capsys
    ) -> None:
        """Con TTY activo y sin flags, el log crudo de Odoo NO va a stdout."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: True)

        fake_popen = FakePopen(_FIXTURE_ALL_PASS, returncode=0)
        mock_dc = MagicMock()
        mock_dc.exec_cmd_stream.return_value = fake_popen

        _call_run_test(tmp_path, mock_dc)

        mock_dc.exec_cmd.assert_not_called()
        captured = capsys.readouterr()
        assert "odoo.addons.sale.tests" not in captured.out


# ---------------------------------------------------------------------------
# T1b — --verbose restaura el stream crudo interactivo
# ---------------------------------------------------------------------------


class TestVerboseFlag:
    """T1b (0.7.0): --verbose restaura el stream crudo en vivo."""

    def test_verbose_en_tty_llama_exec_cmd_interactivo(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """--verbose en TTY → exec_cmd(interactive=True), sin stream/parseo."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: True)

        mock_dc = MagicMock()
        mock_dc.exec_cmd = MagicMock()
        mock_dc.exec_cmd_stream = MagicMock()

        _call_run_test(tmp_path, mock_dc, verbose=True)

        mock_dc.exec_cmd.assert_called_once()
        call_args = mock_dc.exec_cmd.call_args
        interactive_value = call_args[1].get("interactive") or (
            len(call_args[0]) > 2 and call_args[0][2]
        )
        assert interactive_value is True
        mock_dc.exec_cmd_stream.assert_not_called()

    def test_verbose_con_json_exit_2(self, tmp_path: Path, monkeypatch) -> None:
        """--verbose --json es contradictorio → exit 2, sin llamar docker."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: True)

        mock_dc = MagicMock()
        exc = _call_run_test(tmp_path, mock_dc, verbose=True, json_out=True)

        code = exc.code if isinstance(exc, SystemExit) else exc.exit_code
        assert code == 2
        mock_dc.exec_cmd.assert_not_called()
        mock_dc.exec_cmd_stream.assert_not_called()

    def test_verbose_con_summary_exit_2(self, tmp_path: Path, monkeypatch) -> None:
        """--verbose --summary es contradictorio → exit 2."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: True)

        mock_dc = MagicMock()
        exc = _call_run_test(tmp_path, mock_dc, verbose=True, summary=True)

        code = exc.code if isinstance(exc, SystemExit) else exc.exit_code
        assert code == 2

    def test_verbose_con_failures_exit_2(self, tmp_path: Path, monkeypatch) -> None:
        """--verbose --failures es contradictorio → exit 2."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: True)

        mock_dc = MagicMock()
        exc = _call_run_test(tmp_path, mock_dc, verbose=True, failures_only=True)

        code = exc.code if isinstance(exc, SystemExit) else exc.exit_code
        assert code == 2

    def test_verbose_con_save_log_captura_y_streamea(
        self, tmp_path: Path, monkeypatch, capsys
    ) -> None:
        """--verbose --save-log guarda el log crudo Y lo emite en vivo a stdout."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: True)

        fake_popen = FakePopen(_FIXTURE_ALL_PASS, returncode=0)
        mock_dc = MagicMock()
        mock_dc.exec_cmd_stream.return_value = fake_popen

        log_file = tmp_path / "verbose.log"
        _call_run_test(tmp_path, mock_dc, verbose=True, save_log=log_file)

        assert log_file.exists()
        assert "Ran 2 tests" in log_file.read_text()
        captured = capsys.readouterr()
        # El log crudo se streamea a stdout (modo verbose)
        assert "odoo.addons.sale.tests" in captured.out


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
            patch("odev.commands.test.validar_modulo_existe", return_value=None),
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
            patch("odev.commands.test.validar_modulo_existe", return_value=None),
        ):
            mock_rutas.return_value.env_file = tmp_path / ".env"
            try:
                _run_test(**{**_default_run_kwargs(), "module": "sale"})
            except (SystemExit, typer.Exit) as e:
                code = e.code if isinstance(e, SystemExit) else e.exit_code
                assert code == 0


# ---------------------------------------------------------------------------
# T8b — Contrato de exit codes: Odoo 19 devuelve 0 aunque haya tests fallidos
# ---------------------------------------------------------------------------


class TestExitCodeContrato:
    """T8b: el exit code combina returncode del proceso con el resultado parseado.

    Odoo 19 con --test-enable --stop-after-init sale con returncode 0 aunque
    haya failures/errors. El contrato documentado (0=pass, 1=fail/error,
    2=uso, 3=entorno) exige que odev derive el codigo del resultado parseado
    cuando el proceso devuelve 0.
    """

    @staticmethod
    def _codigo(exc) -> int:
        assert exc is not None, "Se esperaba typer.Exit/SystemExit con exit code"
        return exc.code if isinstance(exc, SystemExit) else exc.exit_code

    def test_fallo_con_returncode_cero_sale_1(self, tmp_path: Path, monkeypatch) -> None:
        """Tests con FAIL + proceso Odoo returncode=0 → exit 1."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)

        fake_popen = FakePopen(_FIXTURE_ONE_FAIL, returncode=0)
        mock_dc = MagicMock()
        mock_dc.exec_cmd_stream.return_value = fake_popen

        exc = _call_run_test(tmp_path, mock_dc)

        assert self._codigo(exc) == 1

    def test_error_con_returncode_cero_sale_1(self, tmp_path: Path, monkeypatch) -> None:
        """Tests con ERROR (no failure) + proceso returncode=0 → exit 1."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)

        fake_popen = FakePopen(_FIXTURE_ONE_ERROR, returncode=0)
        mock_dc = MagicMock()
        mock_dc.exec_cmd_stream.return_value = fake_popen

        exc = _call_run_test(tmp_path, mock_dc)

        assert self._codigo(exc) == 1

    def test_salida_no_parseable_con_returncode_cero_sale_1(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """Salida no parseable (parse_failed) + proceso returncode=0 → exit 1."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)

        fake_popen = FakePopen(_FIXTURE_MALFORMED, returncode=0)
        mock_dc = MagicMock()
        mock_dc.exec_cmd_stream.return_value = fake_popen

        exc = _call_run_test(tmp_path, mock_dc)

        assert self._codigo(exc) == 1

    def test_todos_pasan_con_returncode_cero_sale_0(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """Todos los tests pasan + returncode=0 → exit 0 (no regresion)."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)

        fake_popen = FakePopen(_FIXTURE_ALL_PASS, returncode=0)
        mock_dc = MagicMock()
        mock_dc.exec_cmd_stream.return_value = fake_popen

        exc = _call_run_test(tmp_path, mock_dc)

        assert self._codigo(exc) == 0

    def test_proceso_no_cero_manda_aunque_tests_pasen(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """returncode=1 del proceso con ALL_PASS → exit 1 (proceso manda si ≠0)."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)

        fake_popen = FakePopen(_FIXTURE_ALL_PASS, returncode=1)
        mock_dc = MagicMock()
        mock_dc.exec_cmd_stream.return_value = fake_popen

        exc = _call_run_test(tmp_path, mock_dc)

        assert self._codigo(exc) == 1

    def test_puerto_ocupado_sigue_saliendo_3(self, tmp_path: Path, monkeypatch) -> None:
        """'Address already in use' + returncode=0 sigue devolviendo 3 (no 1)."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)

        fake_popen = FakePopen(_FIXTURE_PORT_CONFLICT, returncode=0)
        mock_dc = MagicMock()
        mock_dc.exec_cmd_stream.return_value = fake_popen

        exc = _call_run_test(tmp_path, mock_dc)

        assert self._codigo(exc) == 3

    def test_json_se_emite_antes_del_exit_1(
        self, tmp_path: Path, monkeypatch, capsys
    ) -> None:
        """--json con fallos y returncode=0: emite JSON valido Y sale con 1."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)

        fake_popen = FakePopen(_FIXTURE_ONE_FAIL, returncode=0)
        mock_dc = MagicMock()
        mock_dc.exec_cmd_stream.return_value = fake_popen

        exc = _call_run_test(tmp_path, mock_dc, json_out=True)

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["failed"] == 1
        assert self._codigo(exc) == 1


# ---------------------------------------------------------------------------
# T8c — D11-bis: normalizacion del codigo crudo del proceso Odoo
# ---------------------------------------------------------------------------


class TestNormalizacionExitCodeProceso:
    """Un codigo de proceso fuera del contrato (0/1/2/3) se normaliza a 1.

    'odev test' corria un proceso Odoo dentro del contenedor y propagaba su
    codigo de retorno crudo (137 del OOM killer, 139 de un segfault, lo que
    sea) tal cual, rompiendo el contrato de EPILOG_EXIT_CODES que el resto
    de los comandos respeta. El mapeo es el mismo que usan 'addon-install'
    y 'update' via normalizar_exit_code_odoo: el numero crudo no se pierde,
    queda nombrado en el mensaje de stderr y en 'process_exit_code' del
    JSON.

    Se patchea _stream_and_collect directamente (en vez de FakePopen.returncode)
    porque es el limite exacto donde el codigo de proceso crudo entra a
    _run_test — el mismo boundary que usan los tests de arriba.
    """

    @staticmethod
    def _lineas_ok() -> list[str]:
        return _FIXTURE_ALL_PASS.splitlines(keepends=True)

    def test_codigo_137_normaliza_a_1(self, tmp_path: Path, monkeypatch) -> None:
        """returncode=137 (OOM killer) del proceso Odoo → exit 1, no 137."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)
        mock_dc = MagicMock()

        with patch(
            "odev.commands.test._stream_and_collect",
            return_value=(self._lineas_ok(), 137),
        ):
            exc = _call_run_test(tmp_path, mock_dc)

        assert TestExitCodeContrato._codigo(exc) == 1

    def test_codigo_139_normaliza_a_1(self, tmp_path: Path, monkeypatch) -> None:
        """returncode=139 (segfault) del proceso Odoo → exit 1, no 139."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)
        mock_dc = MagicMock()

        with patch(
            "odev.commands.test._stream_and_collect",
            return_value=(self._lineas_ok(), 139),
        ):
            exc = _call_run_test(tmp_path, mock_dc)

        assert TestExitCodeContrato._codigo(exc) == 1

    def test_codigo_crudo_aparece_en_stderr(
        self, tmp_path: Path, monkeypatch, capsys
    ) -> None:
        """El 137 no se descarta: queda nombrado en el diagnostico de stderr."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)
        mock_dc = MagicMock()

        with patch(
            "odev.commands.test._stream_and_collect",
            return_value=(self._lineas_ok(), 137),
        ):
            _call_run_test(tmp_path, mock_dc)

        captured = capsys.readouterr()
        assert "137" in captured.err

    def test_codigo_crudo_aparece_en_json_process_exit_code(
        self, tmp_path: Path, monkeypatch, capsys
    ) -> None:
        """El JSON preserva el codigo crudo del proceso en 'process_exit_code'
        aunque el exit code final ya haya sido normalizado a 1."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)
        mock_dc = MagicMock()

        with patch(
            "odev.commands.test._stream_and_collect",
            return_value=(self._lineas_ok(), 137),
        ):
            exc = _call_run_test(tmp_path, mock_dc, json_out=True)

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["process_exit_code"] == 137
        assert TestExitCodeContrato._codigo(exc) == 1

    def test_run_limpio_process_exit_code_cero(
        self, tmp_path: Path, monkeypatch, capsys
    ) -> None:
        """Corrida limpia (returncode=0): 'process_exit_code' tambien es 0,
        presente en el payload igual que en cualquier otra corrida."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)
        fake_popen = FakePopen(_FIXTURE_ALL_PASS, returncode=0)
        mock_dc = MagicMock()
        mock_dc.exec_cmd_stream.return_value = fake_popen

        exc = _call_run_test(tmp_path, mock_dc, json_out=True)

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["process_exit_code"] == 0
        assert TestExitCodeContrato._codigo(exc) == 0

    def test_returncode_hint_con_process_exit_code_cero(
        self, tmp_path: Path, monkeypatch, capsys
    ) -> None:
        """returncode=0 con tests fallidos: el exit final sigue viniendo de
        returncode_hint (1), y 'process_exit_code' sigue siendo 0 porque el
        proceso Odoo en si no fallo (D8b, sin regresion)."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)
        fake_popen = FakePopen(_FIXTURE_ONE_FAIL, returncode=0)
        mock_dc = MagicMock()
        mock_dc.exec_cmd_stream.return_value = fake_popen

        exc = _call_run_test(tmp_path, mock_dc, json_out=True)

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["process_exit_code"] == 0
        assert TestExitCodeContrato._codigo(exc) == 1

    def test_puerto_ocupado_no_pasa_por_normalizacion_generica(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """El 3 de puerto ocupado sigue sobreviviendo: no regresion del caso
        ya cubierto por TestExitCodeContrato.test_puerto_ocupado_sigue_saliendo_3,
        verificado aca tambien contra el boundary de _stream_and_collect."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)
        mock_dc = MagicMock()

        with patch(
            "odev.commands.test._stream_and_collect",
            return_value=(_FIXTURE_PORT_CONFLICT.splitlines(keepends=True), 0),
        ):
            exc = _call_run_test(tmp_path, mock_dc)

        assert TestExitCodeContrato._codigo(exc) == 3


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


# ---------------------------------------------------------------------------
# T-module — Module pre-flight (validar_modulo_existe wired in T7)
# ---------------------------------------------------------------------------


class TestModulePreFlight:
    """Pre-flight de modulo: rechaza nombres desconocidos, acepta builtins y 'all'."""

    def test_modulo_inexistente_exit_2(self, tmp_path: Path, monkeypatch) -> None:
        """Modulo no encontrado → typer.Exit(2) y stderr menciona el modulo."""
        import typer

        from odev.commands.test import _run_test

        ctx = _make_contexto(tmp_path)
        addon_dir = tmp_path / "addons"
        addon_dir.mkdir()
        (addon_dir / "invoice_importer_app" / "__manifest__.py").parent.mkdir()
        (addon_dir / "invoice_importer_app" / "__manifest__.py").touch()

        from odev.core.detect import RepoLayout, TipoRepo
        fake_layout = RepoLayout(
            tipo=TipoRepo.MULTI_ADDON,
            rutas_addons=[addon_dir],
            modulos_encontrados=1,
        )

        with (
            patch("odev.commands.test.requerir_proyecto", return_value=ctx),
            patch("odev.commands.test.obtener_rutas") as mock_rutas,
            patch("odev.commands.test.obtener_docker", return_value=MagicMock()),
            patch("odev.commands.test.load_env", return_value={"DB_NAME": "test_db"}),
            patch("odev.main.obtener_nombre_proyecto", return_value="test-project"),
            patch("odev.commands._helpers.detectar_layout", return_value=fake_layout),
        ):
            mock_rutas.return_value.env_file = tmp_path / ".env"
            with pytest.raises((SystemExit, typer.Exit)) as exc_info:
                _run_test(
                    **{**_default_run_kwargs(), "module": "typo_module"}
                )

        exc = exc_info.value
        code = exc.code if isinstance(exc, SystemExit) else exc.exit_code
        assert code == 2

    def test_modulo_builtin_pasa_sin_detect(self, tmp_path: Path, monkeypatch) -> None:
        """Modulo builtin (base) → no llama detectar_layout, command sigue."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)
        from odev.commands.test import _run_test

        ctx = _make_contexto(tmp_path)
        fake_popen = FakePopen(_FIXTURE_ALL_PASS, returncode=0)
        mock_dc = MagicMock()
        mock_dc.exec_cmd_stream.return_value = fake_popen

        with (
            patch("odev.commands.test.requerir_proyecto", return_value=ctx),
            patch("odev.commands.test.obtener_rutas") as mock_rutas,
            patch("odev.commands.test.obtener_docker", return_value=mock_dc),
            patch("odev.commands.test.load_env", return_value={"DB_NAME": "test_db"}),
            patch("odev.main.obtener_nombre_proyecto", return_value="test-project"),
            patch("odev.commands._helpers.detectar_layout") as mock_detect,
        ):
            mock_rutas.return_value.env_file = tmp_path / ".env"
            try:
                _run_test(**{**_default_run_kwargs(), "module": "base"})
            except (SystemExit, Exception) as e:
                import typer
                if isinstance(e, typer.Exit):
                    assert e.exit_code == 0

            # detectar_layout NO debe haberse llamado (builtin bypass)
            mock_detect.assert_not_called()

    def test_modulo_all_bypass(self, tmp_path: Path, monkeypatch) -> None:
        """module='all' → no pre-flight, exec_cmd_stream llamado."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)

        fake_popen = FakePopen(_FIXTURE_ALL_PASS, returncode=0)
        mock_dc = MagicMock()
        mock_dc.exec_cmd_stream.return_value = fake_popen

        with (
            patch("odev.commands._helpers.detectar_layout") as mock_detect,
        ):
            _call_run_test(tmp_path, mock_dc, module="all")
            mock_detect.assert_not_called()
        mock_dc.exec_cmd_stream.assert_called_once()

    def test_modulo_valido_continua(self, tmp_path: Path, monkeypatch) -> None:
        """Modulo encontrado en addons-path → exec_cmd_stream llamado."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)

        addon_dir = tmp_path / "addons"
        addon_dir.mkdir()
        (addon_dir / "my_valid_mod").mkdir()
        (addon_dir / "my_valid_mod" / "__manifest__.py").touch()

        from odev.core.detect import RepoLayout, TipoRepo
        fake_layout = RepoLayout(
            tipo=TipoRepo.MULTI_ADDON,
            rutas_addons=[addon_dir],
            modulos_encontrados=1,
        )
        fake_popen = FakePopen(_FIXTURE_ALL_PASS, returncode=0)
        mock_dc = MagicMock()
        mock_dc.exec_cmd_stream.return_value = fake_popen

        from odev.commands.test import _run_test
        ctx = _make_contexto(tmp_path)
        with (
            patch("odev.commands.test.requerir_proyecto", return_value=ctx),
            patch("odev.commands.test.obtener_rutas") as mock_rutas,
            patch("odev.commands.test.obtener_docker", return_value=mock_dc),
            patch("odev.commands.test.load_env", return_value={"DB_NAME": "test_db"}),
            patch("odev.main.obtener_nombre_proyecto", return_value="test-project"),
            patch("odev.commands._helpers.detectar_layout", return_value=fake_layout),
        ):
            mock_rutas.return_value.env_file = tmp_path / ".env"
            try:
                _run_test(**{**_default_run_kwargs(), "module": "my_valid_mod"})
            except (SystemExit, Exception) as e:
                import typer
                if isinstance(e, typer.Exit):
                    pass

        mock_dc.exec_cmd_stream.assert_called_once()


# ---------------------------------------------------------------------------
# T-port — HTTP service disabled during tests
# ---------------------------------------------------------------------------


class TestHttpDisabled:
    """El comando de tests pasa --no-http + --http-port=8073 para evitar bindear puertos.

    Historia:
    - Pre-0.4.0: pasaba `--http-port=$WEB_PORT`. Cuando WEB_PORT host = 8069
      (default), colisionaba con odoo principal en 8069 interno del container.
    - 0.4.0-0.4.1: solo `--no-http`. Funciono en Odoo <=18 pero Odoo 19 ignora
      `--no-http` y sigue bindeando 8069 interno → "Address already in use".
    - 0.4.2+: `--no-http` (retro-compat <=18) + `--http-port=8073` (Odoo 19
      bindea un puerto interno libre, distinto del 8069 del web container).
    """

    def test_comando_incluye_no_http_y_http_port_libre(self, tmp_path: Path, monkeypatch) -> None:
        """El comando incluye --no-http y --http-port=8073 (Odoo 19 fix)."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)
        from odev.commands.test import _TEST_HTTP_PORT, _run_test

        ctx = _make_contexto(tmp_path)
        fake_popen = FakePopen(_FIXTURE_ALL_PASS, returncode=0)
        mock_dc = MagicMock()
        mock_dc.exec_cmd_stream.return_value = fake_popen

        with (
            patch("odev.commands.test.requerir_proyecto", return_value=ctx),
            patch("odev.commands.test.obtener_rutas") as mock_rutas,
            patch("odev.commands.test.obtener_docker", return_value=mock_dc),
            patch("odev.commands.test.load_env", return_value={"DB_NAME": "test_db"}),
            patch("odev.main.obtener_nombre_proyecto", return_value="test-project"),
            patch("odev.commands.test.validar_modulo_existe", return_value=None),
        ):
            mock_rutas.return_value.env_file = tmp_path / ".env"
            try:
                _run_test(**_default_run_kwargs())
            except (SystemExit, Exception) as e:
                import typer
                if isinstance(e, typer.Exit):
                    pass

        args = mock_dc.exec_cmd_stream.call_args[0]
        cmd_list = args[1]
        assert "--no-http" in cmd_list
        # Odoo 19 ignora --no-http; --http-port=8073 redirige el bind a un puerto
        # interno libre, distinto del 8069 que ocupa el odoo principal.
        assert f"--http-port={_TEST_HTTP_PORT}" in cmd_list
        assert _TEST_HTTP_PORT == 8073


# ---------------------------------------------------------------------------
# T-stream — Stream-level port conflict fallback
# ---------------------------------------------------------------------------


class TestPortConflictStream:
    """Deteccion de conflicto de puerto en stream (TOCTOU guard)."""

    def test_address_in_use_en_stream_fuerza_exit_3(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """returncode=0 + parse_failed=True + 'Address already in use' → exit 3."""
        import typer

        from odev.commands.test import _run_test

        ctx = _make_contexto(tmp_path)
        # Output con Address already in use y sin linea 'Ran N tests'
        fake_popen = FakePopen(_FIXTURE_PORT_CONFLICT, returncode=0)
        mock_dc = MagicMock()
        mock_dc.exec_cmd_stream.return_value = fake_popen

        with (
            patch("odev.commands.test.requerir_proyecto", return_value=ctx),
            patch("odev.commands.test.obtener_rutas") as mock_rutas,
            patch("odev.commands.test.obtener_docker", return_value=mock_dc),
            patch("odev.commands.test.load_env", return_value={"DB_NAME": "test_db"}),
            patch("odev.main.obtener_nombre_proyecto", return_value="test-project"),
            patch("odev.commands.test.validar_modulo_existe", return_value=None),
        ):
            mock_rutas.return_value.env_file = tmp_path / ".env"
            with pytest.raises((SystemExit, typer.Exit)) as exc_info:
                _run_test(**{**_default_run_kwargs(), "summary": True})

        exc = exc_info.value
        code = exc.code if isinstance(exc, SystemExit) else exc.exit_code
        assert code == 3

    def test_address_in_use_con_parse_exitoso_no_fuerza_exit_3(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """parse_failed=False aunque haya 'Address already in use' → exit 0."""
        from odev.commands.test import _run_test

        ctx = _make_contexto(tmp_path)
        # Output con 'Address already in use' PERO tambien tiene 'Ran N tests'
        fixture_con_ran = (
            "2024-01-15 10:00:00,001 1234 INFO odoo.server Address already in use\n"
            "Ran 2 tests in 0.200s\n\nOK\n"
        )
        fake_popen = FakePopen(fixture_con_ran, returncode=0)
        mock_dc = MagicMock()
        mock_dc.exec_cmd_stream.return_value = fake_popen

        with (
            patch("odev.commands.test.requerir_proyecto", return_value=ctx),
            patch("odev.commands.test.obtener_rutas") as mock_rutas,
            patch("odev.commands.test.obtener_docker", return_value=mock_dc),
            patch("odev.commands.test.load_env", return_value={"DB_NAME": "test_db"}),
            patch("odev.main.obtener_nombre_proyecto", return_value="test-project"),
            patch("odev.commands.test.validar_modulo_existe", return_value=None),
        ):
            mock_rutas.return_value.env_file = tmp_path / ".env"
            exc = None
            try:
                _run_test(**{**_default_run_kwargs(), "summary": True})
            except (SystemExit, Exception) as e:
                import typer as t
                if isinstance(e, (SystemExit, t.Exit)):
                    exc = e
                else:
                    raise

        code = exc.code if isinstance(exc, SystemExit) else exc.exit_code if exc else 0
        assert code == 0


# ---------------------------------------------------------------------------
# T-tags — --tags merge into single --test-tags flag
# ---------------------------------------------------------------------------


class TestTagsMerge:
    """Fix de merge de --tags: un solo --test-tags en el comando."""

    def test_modulo_y_tags_produce_un_solo_test_tags(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """module='my_mod' + tags='MyClass' → un solo --test-tags, y su valor es 'MyClass'.

        El prefijo '/my_mod' NO se emite: Odoo une los specs separados por coma,
        asi que '/my_mod,MyClass' significaria "todos los tests de my_mod" O "los
        tagueados MyClass", corriendo el modulo entero. El '-u my_mod' ya acota
        los modulos.
        """
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)

        fake_popen = FakePopen(_FIXTURE_ALL_PASS, returncode=0)
        mock_dc = MagicMock()
        mock_dc.exec_cmd_stream.return_value = fake_popen

        _call_run_test(tmp_path, mock_dc, module="my_mod", tags="MyClass")

        args = mock_dc.exec_cmd_stream.call_args[0]
        cmd_list = args[1]
        test_tags_indices = [i for i, a in enumerate(cmd_list) if a == "--test-tags"]
        assert len(test_tags_indices) == 1, (
            f"Expected exactly 1 --test-tags, got {len(test_tags_indices)}: {cmd_list}"
        )
        assert cmd_list[test_tags_indices[0] + 1] == "MyClass"
        # El modulo se acota por -u, no por el prefijo de tags.
        assert "-u" in cmd_list and cmd_list[cmd_list.index("-u") + 1] == "my_mod"

    def test_modulo_sin_tags_produce_solo_prefijo(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """module='my_mod' sin tags → --test-tags /my_mod (sin coma)."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)

        fake_popen = FakePopen(_FIXTURE_ALL_PASS, returncode=0)
        mock_dc = MagicMock()
        mock_dc.exec_cmd_stream.return_value = fake_popen

        _call_run_test(tmp_path, mock_dc, module="my_mod", tags=None)

        args = mock_dc.exec_cmd_stream.call_args[0]
        cmd_list = args[1]
        test_tags_indices = [i for i, a in enumerate(cmd_list) if a == "--test-tags"]
        assert len(test_tags_indices) == 1
        assert cmd_list[test_tags_indices[0] + 1] == "/my_mod"

    def test_all_con_tags_produce_tag_sin_prefijo(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """module='all' + tags='sale' → --test-tags sale (sin prefijo /all)."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)

        fake_popen = FakePopen(_FIXTURE_ALL_PASS, returncode=0)
        mock_dc = MagicMock()
        mock_dc.exec_cmd_stream.return_value = fake_popen

        _call_run_test(tmp_path, mock_dc, module="all", tags="sale")

        args = mock_dc.exec_cmd_stream.call_args[0]
        cmd_list = args[1]
        test_tags_indices = [i for i, a in enumerate(cmd_list) if a == "--test-tags"]
        assert len(test_tags_indices) == 1
        assert cmd_list[test_tags_indices[0] + 1] == "sale"

    def test_all_sin_tags_no_produce_test_tags(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """module='all' sin tags → --test-tags NO aparece en el comando."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)

        fake_popen = FakePopen(_FIXTURE_ALL_PASS, returncode=0)
        mock_dc = MagicMock()
        mock_dc.exec_cmd_stream.return_value = fake_popen

        _call_run_test(tmp_path, mock_dc, module="all", tags=None)

        args = mock_dc.exec_cmd_stream.call_args[0]
        cmd_list = args[1]
        assert "--test-tags" not in cmd_list


# ---------------------------------------------------------------------------
# T-json-new — raw_summary_line + fallback_counters_used en JSON
# ---------------------------------------------------------------------------


class TestJsonNewFields:
    """Nuevos campos en JSON output: raw_summary_line y fallback_counters_used."""

    def test_json_contiene_raw_summary_line(
        self, tmp_path: Path, monkeypatch, capsys
    ) -> None:
        """--json con fixture v19 → JSON contiene 'raw_summary_line'."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)

        fake_popen = FakePopen(_FIXTURE_V19_CLEAN, returncode=0)
        mock_dc = MagicMock()
        mock_dc.exec_cmd_stream.return_value = fake_popen

        _call_run_test(tmp_path, mock_dc, json_out=True)

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "raw_summary_line" in data

    def test_json_contiene_fallback_counters_used(
        self, tmp_path: Path, monkeypatch, capsys
    ) -> None:
        """--json con fixture v19 → JSON contiene 'fallback_counters_used'."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)

        fake_popen = FakePopen(_FIXTURE_V19_CLEAN, returncode=0)
        mock_dc = MagicMock()
        mock_dc.exec_cmd_stream.return_value = fake_popen

        _call_run_test(tmp_path, mock_dc, json_out=True)

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "fallback_counters_used" in data
        assert isinstance(data["fallback_counters_used"], bool)

    def test_json_fallback_false_en_v14(
        self, tmp_path: Path, monkeypatch, capsys
    ) -> None:
        """--json con fixture v14 → 'fallback_counters_used': false."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)

        fake_popen = FakePopen(_FIXTURE_ALL_PASS, returncode=0)
        mock_dc = MagicMock()
        mock_dc.exec_cmd_stream.return_value = fake_popen

        _call_run_test(tmp_path, mock_dc, json_out=True)

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["fallback_counters_used"] is False


# ---------------------------------------------------------------------------
# T-csv — CSV multi-module support (REQ-5)
# ---------------------------------------------------------------------------


class TestCSVModules:
    """REQ-5: _run_test acepta CSV de modulos y genera invocacion Odoo agregada."""

    def _call_run_test_csv(self, tmp_path: Path, mock_dc: MagicMock, **overrides):
        """Llama _run_test con patches para CSV: no parchea validar_modulo_existe
        sino validar_modulos directamente (nueva implementacion).
        """
        from odev.commands.test import _run_test

        ctx = _make_contexto(tmp_path)
        kwargs = {**_default_run_kwargs(), **overrides}

        exc = None
        with (
            patch("odev.commands.test.requerir_proyecto", return_value=ctx),
            patch("odev.commands.test.obtener_rutas") as mock_rutas,
            patch("odev.commands.test.obtener_docker", return_value=mock_dc),
            patch("odev.commands.test.load_env", return_value={"DB_NAME": "test_db"}),
            patch("odev.main.obtener_nombre_proyecto", return_value="test-project"),
            patch("odev.commands.test.validar_modulos", return_value=None),
        ):
            mock_rutas.return_value.env_file = tmp_path / ".env"
            try:
                _run_test(**kwargs)
            except (SystemExit, Exception) as e:
                import typer as ty
                if isinstance(e, (SystemExit, ty.Exit)):
                    exc = e
                else:
                    raise

        return exc

    def test_5b_csv_genera_u_comma_joined(self, tmp_path: Path, monkeypatch) -> None:
        """5-B: _run_test('m1,m2') → exec_cmd_stream con -u m1,m2 en args."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)

        fake_popen = FakePopen(_FIXTURE_ALL_PASS, returncode=0)
        mock_dc = MagicMock()
        mock_dc.exec_cmd_stream.return_value = fake_popen

        self._call_run_test_csv(
            tmp_path, mock_dc,
            module="m1,m2",
            summary=True,
        )

        cmd = mock_dc.exec_cmd_stream.call_args[0][1]
        assert "-u" in cmd
        idx_u = cmd.index("-u")
        assert cmd[idx_u + 1] == "m1,m2"

    def test_5b_csv_genera_test_tags_con_prefijos(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """5-B: _run_test('m1,m2') → --test-tags /m1,/m2 en args."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)

        fake_popen = FakePopen(_FIXTURE_ALL_PASS, returncode=0)
        mock_dc = MagicMock()
        mock_dc.exec_cmd_stream.return_value = fake_popen

        self._call_run_test_csv(
            tmp_path, mock_dc,
            module="m1,m2",
            summary=True,
        )

        cmd = mock_dc.exec_cmd_stream.call_args[0][1]
        assert "--test-tags" in cmd
        idx_tt = cmd.index("--test-tags")
        assert cmd[idx_tt + 1] == "/m1,/m2"

    def test_5c_tags_reemplaza_prefijos(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """5-C: _run_test('m1,m2', tags='/X:Cls') → --test-tags /X:Cls (reemplaza).

        Los prefijos NO se agregan: Odoo une los specs por coma, asi que
        '/m1,/m2,/X:Cls' correria m1 y m2 enteros ademas del filtro. Los modulos
        siguen acotados por '-u m1,m2'.
        """
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)

        fake_popen = FakePopen(_FIXTURE_ALL_PASS, returncode=0)
        mock_dc = MagicMock()
        mock_dc.exec_cmd_stream.return_value = fake_popen

        self._call_run_test_csv(
            tmp_path, mock_dc,
            module="m1,m2",
            tags="/X:Cls",
            summary=True,
        )

        cmd = mock_dc.exec_cmd_stream.call_args[0][1]
        idx_tt = cmd.index("--test-tags")
        assert cmd[idx_tt + 1] == "/X:Cls"
        assert cmd[cmd.index("-u") + 1] == "m1,m2"

    def test_5d_all_solo_sin_u_sin_test_tags(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """5-D: _run_test('all') → no -u, no --test-tags prefix."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)

        fake_popen = FakePopen(_FIXTURE_ALL_PASS, returncode=0)
        mock_dc = MagicMock()
        mock_dc.exec_cmd_stream.return_value = fake_popen

        self._call_run_test_csv(
            tmp_path, mock_dc,
            module="all",
            summary=True,
        )

        cmd = mock_dc.exec_cmd_stream.call_args[0][1]
        assert "-u" not in cmd
        assert "--test-tags" not in cmd

    def test_5e_all_mezclado_exit_2(self, tmp_path: Path, monkeypatch) -> None:
        """5-E: _run_test('m1,all') → exit 2 antes de llamar Odoo."""
        import typer as ty

        from odev.commands.test import _run_test

        ctx = _make_contexto(tmp_path)
        mock_dc = MagicMock()

        with (
            patch("odev.commands.test.requerir_proyecto", return_value=ctx),
            patch("odev.commands.test.obtener_rutas") as mock_rutas,
            patch("odev.commands.test.obtener_docker", return_value=mock_dc),
            patch("odev.commands.test.load_env", return_value={"DB_NAME": "test_db"}),
            patch("odev.main.obtener_nombre_proyecto", return_value="test-project"),
        ):
            mock_rutas.return_value.env_file = tmp_path / ".env"
            with pytest.raises((SystemExit, ty.Exit)) as exc_info:
                _run_test(
                    **{**_default_run_kwargs(), "module": "m1,all", "no_validate": False}
                )

        exc = exc_info.value
        code = exc.code if isinstance(exc, SystemExit) else exc.exit_code
        assert code == 2
        mock_dc.exec_cmd_stream.assert_not_called()
        mock_dc.exec_cmd.assert_not_called()

    def test_no_validate_bypassa_validacion(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """--no-validate en _run_test bypassa la validacion de modulos."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)

        fake_popen = FakePopen(_FIXTURE_ALL_PASS, returncode=0)
        mock_dc = MagicMock()
        mock_dc.exec_cmd_stream.return_value = fake_popen

        import typer as ty

        from odev.commands.test import _run_test

        ctx = _make_contexto(tmp_path)

        with (
            patch("odev.commands.test.requerir_proyecto", return_value=ctx),
            patch("odev.commands.test.obtener_rutas") as mock_rutas,
            patch("odev.commands.test.obtener_docker", return_value=mock_dc),
            patch("odev.commands.test.load_env", return_value={"DB_NAME": "test_db"}),
            patch("odev.main.obtener_nombre_proyecto", return_value="test-project"),
            patch("odev.commands._helpers.listar_modulos_disponibles", return_value={"sale"}),
        ):
            mock_rutas.return_value.env_file = tmp_path / ".env"
            exc = None
            try:
                _run_test(
                    **{**_default_run_kwargs(), "module": "ghost_mod", "no_validate": True}
                )
            except (SystemExit, ty.Exit) as e:
                exc = e

        # No debe haber salido con exit 2 por validacion
        if exc is not None:
            code = exc.code if isinstance(exc, SystemExit) else exc.exit_code
            assert code != 2
        mock_dc.exec_cmd_stream.assert_called_once()


# ---------------------------------------------------------------------------
# T-shorthand — D8: module:Class.method shorthand parser (Spec C8)
# ---------------------------------------------------------------------------


class TestTargetShorthand:
    """D8: 'module:Class.method' shorthand expands to --test-tags /mod:Class.method.

    Spec C8-1: shorthand expands to test-tags
    Spec C8-2: bare module is backward compatible
    Spec C8-3: class-only shorthand (no method)
    Design D8: CSV+colon rejected with exit 2
    """

    def _call_with_shorthand(self, tmp_path: Path, module: str, monkeypatch):
        """Helper: llama _run_test con el modulo indicado, captura el comando enviado a docker."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)

        from odev.commands.test import _run_test

        ctx = _make_contexto(tmp_path)
        fake_popen = FakePopen(_FIXTURE_ALL_PASS, returncode=0)
        mock_dc = MagicMock()
        mock_dc.exec_cmd_stream.return_value = fake_popen

        with (
            patch("odev.commands.test.requerir_proyecto", return_value=ctx),
            patch("odev.commands.test.obtener_rutas") as mock_rutas,
            patch("odev.commands.test.obtener_docker", return_value=mock_dc),
            patch("odev.commands.test.load_env", return_value={"DB_NAME": "test_db"}),
            patch("odev.main.obtener_nombre_proyecto", return_value="test-project"),
            patch("odev.commands.test.validar_modulos", return_value=None),
        ):
            mock_rutas.return_value.env_file = tmp_path / ".env"
            try:
                _run_test(
                    module=module,
                    log_level="test",
                    summary=True,
                    failures_only=False,
                    json_out=False,
                    tags=None,
                    save_log=None,
                    no_validate=True,
                )
            except (SystemExit, Exception) as e:
                import typer as ty
                if not isinstance(e, (SystemExit, ty.Exit)):
                    raise
        return mock_dc

    def test_shorthand_class_method_expands_to_test_tags(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """C8-1: 'mymod:TestFoo.test_bar' → --test-tags /mymod:TestFoo.test_bar."""
        mock_dc = self._call_with_shorthand(tmp_path, "mymod:TestFoo.test_bar", monkeypatch)

        cmd = mock_dc.exec_cmd_stream.call_args[0][1]
        assert "--test-tags" in cmd
        idx = cmd.index("--test-tags")
        assert "/mymod:TestFoo.test_bar" in cmd[idx + 1]

    def test_shorthand_class_only_expands_to_test_tags(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """C8-3: 'mymod:TestFoo' (class, no method) → --test-tags /mymod:TestFoo."""
        mock_dc = self._call_with_shorthand(tmp_path, "mymod:TestFoo", monkeypatch)

        cmd = mock_dc.exec_cmd_stream.call_args[0][1]
        assert "--test-tags" in cmd
        idx = cmd.index("--test-tags")
        assert "/mymod:TestFoo" in cmd[idx + 1]

    def test_bare_module_backward_compat(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """C8-2: bare 'mymod' (no colon) → backward compat, --test-tags /mymod."""
        mock_dc = self._call_with_shorthand(tmp_path, "mymod", monkeypatch)

        cmd = mock_dc.exec_cmd_stream.call_args[0][1]
        # No shorthand expansion — standard prefix behavior
        assert "--test-tags" in cmd
        idx = cmd.index("--test-tags")
        # Must be plain /mymod (no colon suffix)
        val = cmd[idx + 1]
        assert val == "/mymod"

    def test_csv_con_colon_rechazado_exit_2(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """D8: CSV+colon ('mod1,mod2:Class.method') → exit 2, no docker call."""
        import typer as ty

        from odev.commands.test import _run_test

        ctx = _make_contexto(tmp_path)
        mock_dc = MagicMock()

        with (
            patch("odev.commands.test.requerir_proyecto", return_value=ctx),
            patch("odev.commands.test.obtener_rutas") as mock_rutas,
            patch("odev.commands.test.obtener_docker", return_value=mock_dc),
            patch("odev.commands.test.load_env", return_value={"DB_NAME": "test_db"}),
            patch("odev.main.obtener_nombre_proyecto", return_value="test-project"),
            patch("odev.commands.test.validar_modulos", return_value=None),
        ):
            mock_rutas.return_value.env_file = tmp_path / ".env"
            with pytest.raises((SystemExit, ty.Exit)) as exc_info:
                _run_test(
                    module="mod1,mod2:TestFoo.test_bar",
                    log_level="test",
                    summary=True,
                    failures_only=False,
                    json_out=False,
                    tags=None,
                    save_log=None,
                    no_validate=True,
                )

        exc = exc_info.value
        code = exc.code if isinstance(exc, SystemExit) else exc.exit_code
        assert code == 2
        mock_dc.exec_cmd_stream.assert_not_called()


# ---------------------------------------------------------------------------
# T-tagbuild — _build_test_tags: la coma de --test-tags es OR, no AND
# ---------------------------------------------------------------------------


class TestBuildTestTags:
    """Regresion del bug de union en --test-tags.

    Odoo une los specs separados por coma (odoo/tests/tag_selector.py: check()
    hace any(...) sobre los includes). Emitir el prefijo '/modulo' junto a la
    expresion del usuario ampliaba la seleccion en vez de acotarla, y corria el
    modulo entero ignorando el filtro.
    """

    def test_tags_reemplaza_prefijos_de_modulo(self) -> None:
        """El caso del bug: un modulo + tag NO debe emitir '/modulo'."""
        from odev.commands.test import _build_test_tags

        assert _build_test_tags(["tagtest"], None, "alpha") == ["alpha"]

    def test_tags_reemplaza_prefijos_con_csv(self) -> None:
        """CSV + tag: tampoco se emiten prefijos; '-u' acota los modulos."""
        from odev.commands.test import _build_test_tags

        assert _build_test_tags(["m1", "m2"], None, "alpha") == ["alpha"]

    def test_sin_tags_emite_prefijos_por_modulo(self) -> None:
        """Sin expresion del usuario, los prefijos siguen siendo el filtro."""
        from odev.commands.test import _build_test_tags

        assert _build_test_tags(["m1", "m2"], None, None) == ["/m1", "/m2"]

    def test_shorthand_sin_tags_produce_spec_unico(self) -> None:
        """El shorthand ya era correcto: un solo spec, tag Y clase Y metodo."""
        from odev.commands.test import _build_test_tags

        assert _build_test_tags(["mod"], "TestFoo.test_bar", None) == [
            "/mod:TestFoo.test_bar"
        ]

    def test_all_sin_tags_no_emite_nada(self) -> None:
        """'all' sin tags: no hay --test-tags que emitir."""
        from odev.commands.test import _build_test_tags

        assert _build_test_tags(["all"], None, None) == []

    def test_all_con_tags_emite_solo_la_expresion(self) -> None:
        """'all' + tags ya era correcto; el fix lo deja igual."""
        from odev.commands.test import _build_test_tags

        assert _build_test_tags(["all"], None, "sale") == ["sale"]

    def test_shorthand_con_tags_es_error_de_uso(self) -> None:
        """Combinar shorthand y --tags lanza ValueError, no se descarta en silencio.

        A2/U1: _build_test_tags senaliza con ValueError; es _run_test quien
        lo convierte a stderr + exit 2 (ver TestVerboseJsonRejection/etc.).
        """
        from odev.commands.test import _build_test_tags

        with pytest.raises(ValueError) as exc_info:
            _build_test_tags(["mod"], "TestFoo", "alpha")

        assert "shorthand" in str(exc_info.value)
        assert "--tags" in str(exc_info.value)

    def test_ninguna_salida_contiene_prefijo_junto_a_tags(self) -> None:
        """Invariante del bug: prefijo y expresion del usuario nunca coexisten.

        Es la propiedad que hacia que Odoo corriera el modulo completo.
        """
        from odev.commands.test import _build_test_tags

        for modulos in (["m1"], ["m1", "m2"], ["all"]):
            specs = _build_test_tags(modulos, None, "alpha")
            assert not any(s.startswith("/m") for s in specs), specs


# ---------------------------------------------------------------------------
# A2/U1 — _parse_test_target lanza ValueError; _run_test lo convierte a
# stderr + exit 2. El caso CSV+colon a nivel CLI ya lo cubre
# TestTargetShorthand.test_csv_con_colon_rechazado_exit_2; aca se agregan
# las llamadas directas y el caso 'all:Class' a nivel CLI que faltaban.
# ---------------------------------------------------------------------------


class TestParseTestTargetErrors:
    """_parse_test_target: las dos combinaciones invalidas, llamadas directo."""

    def test_csv_con_colon_lanza_valueerror(self) -> None:
        """CSV+colon ('mod1,mod2:Class.method') lanza ValueError con mensaje."""
        from odev.commands.test import _parse_test_target

        with pytest.raises(ValueError) as exc_info:
            _parse_test_target("mod1,mod2:TestFoo.test_bar")

        mensaje = str(exc_info.value)
        assert "CSV" in mensaje
        assert "--tags" in mensaje

    def test_all_con_clase_lanza_valueerror(self) -> None:
        """'all:Class' lanza ValueError: 'all' no soporta filtro de clase."""
        from odev.commands.test import _parse_test_target

        with pytest.raises(ValueError) as exc_info:
            _parse_test_target("all:TestFoo")

        assert "'all'" in str(exc_info.value)

    def test_bare_module_no_lanza(self) -> None:
        """Sin ':' no hay nada que rechazar (ruta backward-compat)."""
        from odev.commands.test import _parse_test_target

        assert _parse_test_target("mymod") == ("mymod", None)


class TestParseTestTargetCliContract:
    """Mismos rechazos, vistos desde _run_test: stderr + exit 2, Odoo no llamado."""

    def test_all_con_clase_rechazado_cli_exit_2_y_stderr(
        self, tmp_path: Path, capsys
    ) -> None:
        """'odev test all:TestFoo' → exit 2, mensaje sobre 'all' en stderr."""
        import typer as ty

        from odev.commands.test import _run_test

        ctx = _make_contexto(tmp_path)
        mock_dc = MagicMock()

        with (
            patch("odev.commands.test.requerir_proyecto", return_value=ctx),
            patch("odev.commands.test.obtener_rutas") as mock_rutas,
            patch("odev.commands.test.obtener_docker", return_value=mock_dc),
            patch("odev.commands.test.load_env", return_value={"DB_NAME": "test_db"}),
            patch("odev.main.obtener_nombre_proyecto", return_value="test-project"),
        ):
            mock_rutas.return_value.env_file = tmp_path / ".env"
            with pytest.raises((SystemExit, ty.Exit)) as exc_info:
                _run_test(
                    module="all:TestFoo",
                    log_level="test",
                    summary=True,
                    failures_only=False,
                    json_out=False,
                    tags=None,
                    save_log=None,
                )

        exc = exc_info.value
        code = exc.code if isinstance(exc, SystemExit) else exc.exit_code
        assert code == 2
        mock_dc.exec_cmd_stream.assert_not_called()
        captured = capsys.readouterr()
        assert "'all'" in captured.err

    def test_shorthand_con_tags_rechazado_cli_exit_2_y_stderr(
        self, tmp_path: Path, capsys
    ) -> None:
        """'odev test mymod:TestFoo --tags alpha' → exit 2, mensaje en stderr."""
        import typer as ty

        from odev.commands.test import _run_test

        ctx = _make_contexto(tmp_path)
        mock_dc = MagicMock()

        with (
            patch("odev.commands.test.requerir_proyecto", return_value=ctx),
            patch("odev.commands.test.obtener_rutas") as mock_rutas,
            patch("odev.commands.test.obtener_docker", return_value=mock_dc),
            patch("odev.commands.test.load_env", return_value={"DB_NAME": "test_db"}),
            patch("odev.main.obtener_nombre_proyecto", return_value="test-project"),
            patch("odev.commands.test.validar_modulos", return_value=None),
        ):
            mock_rutas.return_value.env_file = tmp_path / ".env"
            with pytest.raises((SystemExit, ty.Exit)) as exc_info:
                _run_test(
                    module="mymod:TestFoo",
                    log_level="test",
                    summary=True,
                    failures_only=False,
                    json_out=False,
                    tags="alpha",
                    save_log=None,
                )

        exc = exc_info.value
        code = exc.code if isinstance(exc, SystemExit) else exc.exit_code
        assert code == 2
        mock_dc.exec_cmd_stream.assert_not_called()
        captured = capsys.readouterr()
        assert "shorthand" in captured.err
        assert "--tags" in captured.err

    def test_modulo_no_encontrado_cli_mensaje_completo_en_stderr(
        self, tmp_path: Path, capsys
    ) -> None:
        """A2: el mensaje completo de validar_modulos llega a stderr, no un '2'.

        Es la regresion concreta de A2: antes de este cambio typer.Exit(2)
        se comia el mensaje real y solo dejaba pasar el codigo de salida.
        """
        import typer as ty

        from odev.commands.test import _run_test
        from odev.core.detect import RepoLayout, TipoRepo

        ctx = _make_contexto(tmp_path)
        mock_dc = MagicMock()
        fake_layout = RepoLayout(
            tipo=TipoRepo.DESCONOCIDO,
            rutas_addons=[],
            modulos_encontrados=0,
        )

        with (
            patch("odev.commands.test.requerir_proyecto", return_value=ctx),
            patch("odev.commands.test.obtener_rutas") as mock_rutas,
            patch("odev.commands.test.obtener_docker", return_value=mock_dc),
            patch("odev.commands.test.load_env", return_value={"DB_NAME": "test_db"}),
            patch("odev.main.obtener_nombre_proyecto", return_value="test-project"),
            patch(
                "odev.commands._helpers.listar_modulos_disponibles",
                return_value={"sale", "crm"},
            ),
            patch("odev.commands._helpers.detectar_layout", return_value=fake_layout),
        ):
            mock_rutas.return_value.env_file = tmp_path / ".env"
            with pytest.raises((SystemExit, ty.Exit)) as exc_info:
                _run_test(
                    module="ghost_mod",
                    log_level="test",
                    summary=True,
                    failures_only=False,
                    json_out=False,
                    tags=None,
                    save_log=None,
                )

        exc = exc_info.value
        code = exc.code if isinstance(exc, SystemExit) else exc.exit_code
        assert code == 2
        mock_dc.exec_cmd_stream.assert_not_called()
        captured = capsys.readouterr()
        assert "Modulos no encontrados: ghost_mod" in captured.err


# ---------------------------------------------------------------------------
# C3 (mitad test) — el rechazo temprano de --verbose honra --json
# ---------------------------------------------------------------------------


class TestVerboseJsonRejection:
    """El rechazo de --verbose + --json/--summary/--failures va al formato pedido."""

    def test_verbose_json_emite_json_en_stderr_nada_en_stdout(self, capsys) -> None:
        """'odev test mod --verbose --json' → JSON en stderr, stdout vacio."""
        import typer

        from odev.commands.test import _run_test

        with pytest.raises((SystemExit, typer.Exit)) as exc_info:
            _run_test(
                module="mod",
                log_level="test",
                summary=False,
                failures_only=False,
                json_out=True,
                tags=None,
                save_log=None,
                verbose=True,
            )

        exc = exc_info.value
        code = exc.code if isinstance(exc, SystemExit) else exc.exit_code
        assert code == 2

        captured = capsys.readouterr()
        assert captured.out == ""
        payload = json.loads(captured.err)
        assert "error" in payload
        assert "--verbose" in payload["error"]

    def test_verbose_summary_sin_json_va_a_stderr(self, capsys) -> None:
        """Sin --json, el mensaje humano tambien va a stderr, nunca a stdout."""
        import typer

        from odev.commands.test import _run_test

        with pytest.raises((SystemExit, typer.Exit)) as exc_info:
            _run_test(
                module="mod",
                log_level="test",
                summary=True,
                failures_only=False,
                json_out=False,
                tags=None,
                save_log=None,
                verbose=True,
            )

        exc = exc_info.value
        code = exc.code if isinstance(exc, SystemExit) else exc.exit_code
        assert code == 2

        captured = capsys.readouterr()
        assert captured.out == ""
        assert "--verbose" in captured.err

    def test_verbose_failures_sin_json_va_a_stderr(self, capsys) -> None:
        """Idem con --failures en vez de --summary: mismo destino, stderr."""
        import typer

        from odev.commands.test import _run_test

        with pytest.raises((SystemExit, typer.Exit)) as exc_info:
            _run_test(
                module="mod",
                log_level="test",
                summary=False,
                failures_only=True,
                json_out=False,
                tags=None,
                save_log=None,
                verbose=True,
            )

        exc = exc_info.value
        code = exc.code if isinstance(exc, SystemExit) else exc.exit_code
        assert code == 2

        captured = capsys.readouterr()
        assert captured.out == ""
        assert "--verbose" in captured.err


# ---------------------------------------------------------------------------
# A1-a (U2) — warning por stderr cuando la corrida ejecuto cero tests
# ---------------------------------------------------------------------------


class TestZeroTestWarning:
    """0 tests ejecutados es indistinguible de exito si nadie avisa."""

    def test_total_cero_emite_warning_en_stderr(self, tmp_path: Path, capsys) -> None:
        """total==0 y parse_failed==False → warning nombrando el filtro efectivo."""
        from odev.core.test_parser import TestResult

        fake_popen = FakePopen(_FIXTURE_ALL_PASS, returncode=0)
        mock_dc = MagicMock()
        mock_dc.exec_cmd_stream.return_value = fake_popen

        with patch(
            "odev.commands.test.parse_odoo_test_output",
            return_value=TestResult(total=0, duration=0.05),
        ):
            _call_run_test(tmp_path, mock_dc, module="sale")

        captured = capsys.readouterr()
        assert "0 tests" in captured.err
        assert "sale" in captured.err

    def test_total_mayor_a_cero_no_emite_warning(
        self, tmp_path: Path, capsys
    ) -> None:
        """Una corrida con tests reales no dispara el warning de cero tests."""
        fake_popen = FakePopen(_FIXTURE_ALL_PASS, returncode=0)
        mock_dc = MagicMock()
        mock_dc.exec_cmd_stream.return_value = fake_popen

        _call_run_test(tmp_path, mock_dc, module="sale")

        captured = capsys.readouterr()
        assert "0 tests" not in captured.err

    def test_warning_no_contamina_stdout_en_json(
        self, tmp_path: Path, capsys
    ) -> None:
        """Con --json, el warning va a stderr y stdout sigue siendo JSON puro."""
        from odev.core.test_parser import TestResult

        fake_popen = FakePopen(_FIXTURE_ALL_PASS, returncode=0)
        mock_dc = MagicMock()
        mock_dc.exec_cmd_stream.return_value = fake_popen

        with patch(
            "odev.commands.test.parse_odoo_test_output",
            return_value=TestResult(total=0, duration=0.05),
        ):
            _call_run_test(tmp_path, mock_dc, module="sale", json_out=True)

        captured = capsys.readouterr()
        payload = json.loads(captured.out)
        assert payload["total"] == 0
        assert "0 tests" in captured.err

    def test_parse_failed_no_duplica_el_warning(
        self, tmp_path: Path, capsys
    ) -> None:
        """parse_failed==True ya tiene su propio aviso; no se agrega el de A1-a."""
        from odev.core.test_parser import TestResult

        fake_popen = FakePopen(_FIXTURE_MALFORMED, returncode=0)
        mock_dc = MagicMock()
        mock_dc.exec_cmd_stream.return_value = fake_popen

        with patch(
            "odev.commands.test.parse_odoo_test_output",
            return_value=TestResult(total=0, parse_failed=True, raw_output="boom"),
        ):
            _call_run_test(tmp_path, mock_dc, module="sale")

        captured = capsys.readouterr()
        assert "Filtro efectivo" not in captured.err

    def test_modulo_legitimamente_sin_tests_sigue_saliendo_0(
        self, tmp_path: Path
    ) -> None:
        """El warning es advertencia, no error: exit code se mantiene en 0."""
        import typer

        from odev.core.test_parser import TestResult

        fake_popen = FakePopen(_FIXTURE_ALL_PASS, returncode=0)
        mock_dc = MagicMock()
        mock_dc.exec_cmd_stream.return_value = fake_popen

        with patch(
            "odev.commands.test.parse_odoo_test_output",
            return_value=TestResult(total=0, duration=0.05),
        ):
            exc = _call_run_test(tmp_path, mock_dc, module="sale")

        assert isinstance(exc, (type(None), typer.Exit))
        if exc is not None:
            assert exc.exit_code == 0


# ---------------------------------------------------------------------------
# A1-b (U2) — lint de descubrimiento: test_*.py huerfanos de __init__.py
# ---------------------------------------------------------------------------


class TestLintDescubrimientoTests:
    """Compara tests/test_*.py contra lo importado en tests/__init__.py."""

    def _make_ctx(self, tmp_path: Path) -> MagicMock:
        ctx = MagicMock()
        ctx.directorio_config = tmp_path
        return ctx

    def test_detecta_archivo_huerfano(self, tmp_path: Path, capsys) -> None:
        """Un test_*.py no importado dispara un warning que lo nombra."""
        from odev.commands.test import _lint_descubrimiento_tests

        addon_dir = tmp_path / "mymod"
        tests_dir = addon_dir / "tests"
        tests_dir.mkdir(parents=True)
        (tests_dir / "test_imported.py").write_text("class T:\n    pass\n")
        (tests_dir / "test_orphan.py").write_text("class T:\n    pass\n")
        (tests_dir / "__init__.py").write_text("from . import test_imported\n")

        ctx = self._make_ctx(tmp_path)
        with patch("odev.commands.test.resolver_addon_dir", return_value=addon_dir):
            _lint_descubrimiento_tests(["mymod"], ctx)

        captured = capsys.readouterr()
        assert "test_orphan" in captured.err
        assert "test_imported" not in captured.err

    def test_todo_importado_no_avisa(self, tmp_path: Path, capsys) -> None:
        """'from . import a' en lineas separadas: ambos cuentan como importados."""
        from odev.commands.test import _lint_descubrimiento_tests

        addon_dir = tmp_path / "mymod"
        tests_dir = addon_dir / "tests"
        tests_dir.mkdir(parents=True)
        (tests_dir / "test_a.py").write_text("class T:\n    pass\n")
        (tests_dir / "test_b.py").write_text("class T:\n    pass\n")
        (tests_dir / "__init__.py").write_text(
            "from . import test_a\nfrom . import test_b\n"
        )

        ctx = self._make_ctx(tmp_path)
        with patch("odev.commands.test.resolver_addon_dir", return_value=addon_dir):
            _lint_descubrimiento_tests(["mymod"], ctx)

        assert capsys.readouterr().err == ""

    def test_import_csv_en_una_linea_no_reporta_huerfano(
        self, tmp_path: Path, capsys
    ) -> None:
        """'from . import a, b' en una sola linea: ambos cuentan como importados."""
        from odev.commands.test import _lint_descubrimiento_tests

        addon_dir = tmp_path / "mymod"
        tests_dir = addon_dir / "tests"
        tests_dir.mkdir(parents=True)
        (tests_dir / "test_a.py").write_text("class T:\n    pass\n")
        (tests_dir / "test_b.py").write_text("class T:\n    pass\n")
        (tests_dir / "__init__.py").write_text("from . import test_a, test_b\n")

        ctx = self._make_ctx(tmp_path)
        with patch("odev.commands.test.resolver_addon_dir", return_value=addon_dir):
            _lint_descubrimiento_tests(["mymod"], ctx)

        assert capsys.readouterr().err == ""

    def test_import_condicional_cuenta_como_importado(
        self, tmp_path: Path, capsys
    ) -> None:
        """Un import dentro de un 'if': ast.walk lo encuentra igual."""
        from odev.commands.test import _lint_descubrimiento_tests

        addon_dir = tmp_path / "mymod"
        tests_dir = addon_dir / "tests"
        tests_dir.mkdir(parents=True)
        (tests_dir / "test_a.py").write_text("class T:\n    pass\n")
        (tests_dir / "__init__.py").write_text(
            "import sys\nif sys.version_info >= (3, 0):\n    from . import test_a\n"
        )

        ctx = self._make_ctx(tmp_path)
        with patch("odev.commands.test.resolver_addon_dir", return_value=addon_dir):
            _lint_descubrimiento_tests(["mymod"], ctx)

        assert capsys.readouterr().err == ""

    def test_init_no_parseable_omite_en_silencio(
        self, tmp_path: Path, capsys
    ) -> None:
        """__init__.py con SyntaxError: se omite el lint, no se adivina."""
        from odev.commands.test import _lint_descubrimiento_tests

        addon_dir = tmp_path / "mymod"
        tests_dir = addon_dir / "tests"
        tests_dir.mkdir(parents=True)
        (tests_dir / "test_orphan.py").write_text("class T:\n    pass\n")
        (tests_dir / "__init__.py").write_text("def broken(:\n")

        ctx = self._make_ctx(tmp_path)
        with patch("odev.commands.test.resolver_addon_dir", return_value=addon_dir):
            _lint_descubrimiento_tests(["mymod"], ctx)

        assert capsys.readouterr().err == ""

    def test_sin_carpeta_tests_no_avisa(self, tmp_path: Path, capsys) -> None:
        """Modulo legitimamente sin tests/: no hay nada que lintear."""
        from odev.commands.test import _lint_descubrimiento_tests

        addon_dir = tmp_path / "mymod"
        addon_dir.mkdir()

        ctx = self._make_ctx(tmp_path)
        with patch("odev.commands.test.resolver_addon_dir", return_value=addon_dir):
            _lint_descubrimiento_tests(["mymod"], ctx)

        assert capsys.readouterr().err == ""

    def test_target_all_omite_el_lint_por_completo(
        self, tmp_path: Path, capsys
    ) -> None:
        """'all' nunca dispara el lint: ni siquiera resuelve addon dirs."""
        from odev.commands.test import _lint_descubrimiento_tests

        ctx = self._make_ctx(tmp_path)
        with patch("odev.commands.test.resolver_addon_dir") as mock_resolver:
            _lint_descubrimiento_tests(["all"], ctx)
            mock_resolver.assert_not_called()

        assert capsys.readouterr().err == ""

    def test_addon_dir_no_resuelto_no_avisa(self, tmp_path: Path, capsys) -> None:
        """Modulo sin presencia en el addons-path (p.ej. builtin): se omite."""
        from odev.commands.test import _lint_descubrimiento_tests

        ctx = self._make_ctx(tmp_path)
        with patch("odev.commands.test.resolver_addon_dir", return_value=None):
            _lint_descubrimiento_tests(["mymod"], ctx)

        assert capsys.readouterr().err == ""
