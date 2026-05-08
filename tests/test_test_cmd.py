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
      - puerto_disponible: retorna True (puerto libre por defecto)
    Los tests especificos de esas rutas deben pasarlos como 'overrides'
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
        patch("odev.commands.test.puerto_disponible", return_value=True),
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
            patch("odev.commands.test.validar_modulo_existe", return_value=None),
            patch("odev.commands.test.puerto_disponible", return_value=True),
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
            patch("odev.commands.test.puerto_disponible", return_value=True),
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
            patch("odev.commands.test.puerto_disponible", return_value=True),
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
            patch("odev.commands.test.puerto_disponible", return_value=True),
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
            patch("odev.commands.test.puerto_disponible", return_value=True),
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
# T-port — Port pre-flight (WEB_PORT env + puerto_disponible)
# ---------------------------------------------------------------------------


class TestPortPreFlight:
    """Pre-flight de puerto: respeta WEB_PORT, sale con exit 3 si ocupado."""

    def test_puerto_ocupado_exit_3(self, tmp_path: Path, monkeypatch) -> None:
        """puerto_disponible=False → typer.Exit(3), exec_cmd_stream no llamado."""
        import typer

        from odev.commands.test import _run_test

        ctx = _make_contexto(tmp_path)
        mock_dc = MagicMock()

        with (
            patch("odev.commands.test.requerir_proyecto", return_value=ctx),
            patch("odev.commands.test.obtener_rutas") as mock_rutas,
            patch("odev.commands.test.obtener_docker", return_value=mock_dc),
            patch("odev.commands.test.load_env", return_value={"DB_NAME": "test_db"}),
            patch("odev.main.obtener_nombre_proyecto", return_value="test-project"),
            patch("odev.commands.test.validar_modulo_existe", return_value=None),
            patch("odev.commands.test.puerto_disponible", return_value=False),
        ):
            mock_rutas.return_value.env_file = tmp_path / ".env"
            with pytest.raises((SystemExit, typer.Exit)) as exc_info:
                _run_test(**_default_run_kwargs())

        exc = exc_info.value
        code = exc.code if isinstance(exc, SystemExit) else exc.exit_code
        assert code == 3
        mock_dc.exec_cmd_stream.assert_not_called()

    def test_puerto_libre_usa_web_port(self, tmp_path: Path, monkeypatch) -> None:
        """WEB_PORT=9070 libre → comando incluye --http-port=9070."""
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
            patch(
                "odev.commands.test.load_env",
                return_value={"DB_NAME": "test_db", "WEB_PORT": "9070"},
            ),
            patch("odev.main.obtener_nombre_proyecto", return_value="test-project"),
            patch("odev.commands.test.validar_modulo_existe", return_value=None),
            patch("odev.commands.test.puerto_disponible", return_value=True),
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
        assert "--http-port=9070" in cmd_list

    def test_puerto_default_8069(self, tmp_path: Path, monkeypatch) -> None:
        """Sin WEB_PORT en env → comando usa --http-port=8069."""
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
            patch("odev.commands.test.validar_modulo_existe", return_value=None),
            patch("odev.commands.test.puerto_disponible", return_value=True),
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
        assert "--http-port=8069" in cmd_list


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
            patch("odev.commands.test.puerto_disponible", return_value=True),
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
            patch("odev.commands.test.puerto_disponible", return_value=True),
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
        """module='my_mod' + tags='MyClass' → exactamente un --test-tags /my_mod,MyClass."""
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
        assert cmd_list[test_tags_indices[0] + 1] == "/my_mod,MyClass"

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
            patch("odev.commands.test.puerto_disponible", return_value=True),
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

    def test_5c_tags_override_reemplaza_prefijos(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """5-C: _run_test('m1,m2', tags='/X:Cls') → --test-tags /m1,/m2,/X:Cls."""
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
        assert cmd[idx_tt + 1] == "/m1,/m2,/X:Cls"

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
        from odev.commands.test import _run_test
        import typer as ty

        ctx = _make_contexto(tmp_path)
        mock_dc = MagicMock()

        with (
            patch("odev.commands.test.requerir_proyecto", return_value=ctx),
            patch("odev.commands.test.obtener_rutas") as mock_rutas,
            patch("odev.commands.test.obtener_docker", return_value=mock_dc),
            patch("odev.commands.test.load_env", return_value={"DB_NAME": "test_db"}),
            patch("odev.main.obtener_nombre_proyecto", return_value="test-project"),
            patch("odev.commands.test.puerto_disponible", return_value=True),
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

        from odev.commands.test import _run_test
        import typer as ty

        ctx = _make_contexto(tmp_path)

        with (
            patch("odev.commands.test.requerir_proyecto", return_value=ctx),
            patch("odev.commands.test.obtener_rutas") as mock_rutas,
            patch("odev.commands.test.obtener_docker", return_value=mock_dc),
            patch("odev.commands.test.load_env", return_value={"DB_NAME": "test_db"}),
            patch("odev.main.obtener_nombre_proyecto", return_value="test-project"),
            patch("odev.commands._helpers.listar_modulos_disponibles", return_value={"sale"}),
            patch("odev.commands.test.puerto_disponible", return_value=True),
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
