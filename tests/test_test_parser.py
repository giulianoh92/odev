"""Tests para odev.core.test_parser — parser de salida de tests Odoo.

Verifica el parseo de distintos formatos de salida de tests Odoo (v14-v18):
corridas exitosas, fallos, errores, salida mixta, salida malformada y entrada vacia.
"""

import pytest

from odev.core.test_parser import TestFailure, TestResult, parse_odoo_test_output

# ---------------------------------------------------------------------------
# Fixtures — raw log strings imitando salida real de Odoo test runner
# ---------------------------------------------------------------------------

FIXTURE_A_ALL_PASS = """\
2024-01-15 10:00:00,001 1234 INFO odoo.addons.sale.tests.test_sale_order TestSaleOrder.test_create: Starting test
2024-01-15 10:00:00,100 1234 INFO odoo.addons.sale.tests.test_sale_order TestSaleOrder.test_create: Finished
2024-01-15 10:00:00,200 1234 INFO odoo.addons.sale.tests.test_sale_order TestSaleOrder.test_cancel: Starting test
2024-01-15 10:00:00,300 1234 INFO odoo.addons.sale.tests.test_sale_order TestSaleOrder.test_cancel: Finished
2024-01-15 10:00:00,400 1234 INFO odoo.addons.account.tests.test_account_move TestAccountMove.test_post: Starting test
2024-01-15 10:00:00,500 1234 INFO odoo.addons.account.tests.test_account_move TestAccountMove.test_post: Finished
Ran 6 tests in 0.500s

OK
"""

FIXTURE_B_ONE_FAIL = """\
2024-01-15 10:00:00,001 1234 INFO odoo.addons.sale.tests.test_sale_order TestSaleOrder.test_create: Starting test
2024-01-15 10:00:01,000 1234 ERROR odoo.addons.sale.tests.test_sale_order FAIL: TestSaleOrder.test_create
Traceback (most recent call last):
  File "/odoo/addons/sale/tests/test_sale_order.py", line 42, in test_create
    self.assertEqual(order.state, "sale")
AssertionError: 'draft' != 'sale'
2024-01-15 10:00:01,100 1234 INFO odoo.addons.sale.tests.test_sale_order TestSaleOrder.test_cancel: Starting test
2024-01-15 10:00:01,200 1234 INFO odoo.addons.sale.tests.test_sale_order TestSaleOrder.test_cancel: Finished
Ran 2 tests in 1.200s

FAILED (failures=1)
"""

FIXTURE_C_ONE_ERROR = """\
2024-01-15 10:00:00,001 1234 INFO odoo.addons.sale.tests.test_sale_order TestSaleOrder.test_compute: Starting test
2024-01-15 10:00:00,100 1234 ERROR odoo.addons.sale.tests.test_sale_order ERROR: TestSaleOrder.test_compute
Traceback (most recent call last):
  File "/odoo/addons/sale/tests/test_sale_order.py", line 87, in test_compute
    result = self.env["sale.order"].compute()
  File "/odoo/addons/sale/models/sale_order.py", line 123, in compute
    raise ValueError("unexpected state")
ValueError: unexpected state
2024-01-15 10:00:00,200 1234 INFO odoo.addons.sale.tests.test_sale_order TestSaleOrder.test_pass: Finished
Ran 2 tests in 0.200s

FAILED (errors=1)
"""

FIXTURE_D_MIXED_FAIL_ERROR = """\
2024-01-15 10:00:00,001 1234 ERROR odoo.addons.sale.tests.test_sale_order FAIL: TestSaleOrder.test_create
Traceback (most recent call last):
  File "/odoo/addons/sale/tests/test_sale_order.py", line 42, in test_create
    self.assertEqual(order.state, "sale")
AssertionError: 'draft' != 'sale'
2024-01-15 10:00:01,000 1234 ERROR odoo.addons.sale.tests.test_sale_order ERROR: TestSaleOrder.test_compute
Traceback (most recent call last):
  File "/odoo/addons/sale/tests/test_sale_order.py", line 87, in test_compute
    raise ValueError("unexpected state")
ValueError: unexpected state
2024-01-15 10:00:02,000 1234 INFO odoo.addons.sale.tests.test_sale_order TestSaleOrder.test_pass: Finished
Ran 3 tests in 2.000s

FAILED (failures=1, errors=1)
"""

FIXTURE_E_MALFORMED = """\
2024-01-15 10:00:00,001 1234 INFO odoo.modules.loading Loading module sale (1/42)
2024-01-15 10:00:00,100 1234 INFO odoo.modules.loading Loading module account (2/42)
Process crashed before tests could run
"""

FIXTURE_F_EMPTY = ""

# Fixture G: Odoo v19 format — xfail until real v19 fixture confirmed
FIXTURE_G_V19 = """\
2024-01-15 10:00:00,001 1234 ERROR odoo.addons.sale.tests.test_sale_order FAIL: TestSaleOrder.test_create
Traceback (most recent call last):
  File "/odoo/addons/sale/tests/test_sale_order.py", line 42, in test_create
    self.fail("not implemented yet")
AssertionError: not implemented yet
Ran 3 tests in 1.500s

FAILED (failures=1, errors=0)
"""


# ---------------------------------------------------------------------------
# Tests — Fixture A: all pass
# ---------------------------------------------------------------------------


class TestFixtureAAllPass:
    """Fixture A: corrida exitosa con 6 tests."""

    def test_total_correcto(self):
        """Parsea total=6 de 'Ran 6 tests'."""
        result = parse_odoo_test_output(FIXTURE_A_ALL_PASS.splitlines(keepends=True))
        assert result.total == 6

    def test_sin_fallos(self):
        """Failed=0 y errors=0 en corrida exitosa."""
        result = parse_odoo_test_output(FIXTURE_A_ALL_PASS.splitlines(keepends=True))
        assert result.failed == 0
        assert result.errors == 0

    def test_parse_no_fallo(self):
        """parse_failed=False cuando el output es valido."""
        result = parse_odoo_test_output(FIXTURE_A_ALL_PASS.splitlines(keepends=True))
        assert result.parse_failed is False

    def test_duracion_parseada(self):
        """Duracion extraida correctamente de '0.500s'."""
        result = parse_odoo_test_output(FIXTURE_A_ALL_PASS.splitlines(keepends=True))
        assert result.duration == pytest.approx(0.5)

    def test_lista_failures_vacia(self):
        """failures[] vacia cuando no hay fallos."""
        result = parse_odoo_test_output(FIXTURE_A_ALL_PASS.splitlines(keepends=True))
        assert len(result.failures) == 0

    def test_passed_calculado(self):
        """passed = total - failed - errors."""
        result = parse_odoo_test_output(FIXTURE_A_ALL_PASS.splitlines(keepends=True))
        assert result.passed == 6


# ---------------------------------------------------------------------------
# Tests — Fixture B: one FAIL
# ---------------------------------------------------------------------------


class TestFixtureBOneFail:
    """Fixture B: una corrida con un fallo."""

    def test_kind_es_fail(self):
        """El failure tiene kind='FAIL'."""
        result = parse_odoo_test_output(FIXTURE_B_ONE_FAIL.splitlines(keepends=True))
        assert len(result.failures) == 1
        assert result.failures[0].kind == "FAIL"

    def test_test_class_parseado(self):
        """test_class extraido de la linea FAIL."""
        result = parse_odoo_test_output(FIXTURE_B_ONE_FAIL.splitlines(keepends=True))
        assert result.failures[0].test_class == "TestSaleOrder"

    def test_method_parseado(self):
        """method extraido de la linea FAIL."""
        result = parse_odoo_test_output(FIXTURE_B_ONE_FAIL.splitlines(keepends=True))
        assert result.failures[0].method == "test_create"

    def test_traceback_no_vacio(self):
        """traceback contiene el contenido del error."""
        result = parse_odoo_test_output(FIXTURE_B_ONE_FAIL.splitlines(keepends=True))
        assert len(result.failures[0].traceback) > 0
        assert "AssertionError" in result.failures[0].traceback

    def test_failed_count_correcto(self):
        """failed=1 extraido de FAILED (failures=1)."""
        result = parse_odoo_test_output(FIXTURE_B_ONE_FAIL.splitlines(keepends=True))
        assert result.failed == 1

    def test_total_correcto(self):
        """total=2 de 'Ran 2 tests'."""
        result = parse_odoo_test_output(FIXTURE_B_ONE_FAIL.splitlines(keepends=True))
        assert result.total == 2


# ---------------------------------------------------------------------------
# Tests — Fixture C: one ERROR
# ---------------------------------------------------------------------------


class TestFixtureCOneError:
    """Fixture C: una corrida con un error de excepcion."""

    def test_kind_es_error(self):
        """El failure tiene kind='ERROR'."""
        result = parse_odoo_test_output(FIXTURE_C_ONE_ERROR.splitlines(keepends=True))
        assert len(result.failures) == 1
        assert result.failures[0].kind == "ERROR"

    def test_errors_count_correcto(self):
        """errors=1 extraido de FAILED (errors=1)."""
        result = parse_odoo_test_output(FIXTURE_C_ONE_ERROR.splitlines(keepends=True))
        assert result.errors == 1

    def test_traceback_contiene_excepcion(self):
        """traceback contiene el tipo de excepcion."""
        result = parse_odoo_test_output(FIXTURE_C_ONE_ERROR.splitlines(keepends=True))
        assert "ValueError" in result.failures[0].traceback


# ---------------------------------------------------------------------------
# Tests — Fixture D: mixed FAIL + ERROR
# ---------------------------------------------------------------------------


class TestFixtureDMixedFailError:
    """Fixture D: corrida con 1 FAIL + 1 ERROR."""

    def test_dos_failures(self):
        """failures[] tiene exactamente 2 entradas."""
        result = parse_odoo_test_output(FIXTURE_D_MIXED_FAIL_ERROR.splitlines(keepends=True))
        assert len(result.failures) == 2

    def test_failed_y_errors_separados(self):
        """failed=1 y errors=1 independientes."""
        result = parse_odoo_test_output(FIXTURE_D_MIXED_FAIL_ERROR.splitlines(keepends=True))
        assert result.failed == 1
        assert result.errors == 1

    def test_kinds_correctos(self):
        """Los dos failures tienen kinds FAIL y ERROR."""
        result = parse_odoo_test_output(FIXTURE_D_MIXED_FAIL_ERROR.splitlines(keepends=True))
        kinds = {f.kind for f in result.failures}
        assert "FAIL" in kinds
        assert "ERROR" in kinds


# ---------------------------------------------------------------------------
# Tests — Fixture E: malformed output (no 'Ran X tests' line)
# ---------------------------------------------------------------------------


class TestFixtureEMalformed:
    """Fixture E: salida sin linea 'Ran X tests' — debe activar fallback."""

    def test_parse_failed_true(self):
        """parse_failed=True cuando no hay linea 'Ran X tests'."""
        result = parse_odoo_test_output(FIXTURE_E_MALFORMED.splitlines(keepends=True))
        assert result.parse_failed is True

    def test_raw_output_no_vacio(self):
        """raw_output contiene la salida original cuando parse falla."""
        result = parse_odoo_test_output(FIXTURE_E_MALFORMED.splitlines(keepends=True))
        assert len(result.raw_output) > 0
        assert "odoo.modules.loading" in result.raw_output


# ---------------------------------------------------------------------------
# Tests — Fixture F: empty input
# ---------------------------------------------------------------------------


class TestFixtureFEmpty:
    """Fixture F: entrada vacia — debe activar fallback."""

    def test_parse_failed_true_en_entrada_vacia(self):
        """parse_failed=True cuando la entrada esta vacia."""
        result = parse_odoo_test_output([])
        assert result.parse_failed is True

    def test_raw_output_vacio_en_entrada_vacia(self):
        """raw_output vacio cuando no se recibieron lineas."""
        result = parse_odoo_test_output([])
        assert result.raw_output == ""


# ---------------------------------------------------------------------------
# Tests — returncode_hint property
# ---------------------------------------------------------------------------


class TestReturnCodeHint:
    """Tests para la propiedad returncode_hint de TestResult."""

    def test_hint_cero_cuando_todo_pasa(self):
        """returncode_hint=0 cuando failed=0, errors=0, parse_failed=False."""
        r = TestResult(total=3, passed=3, failed=0, errors=0, parse_failed=False)
        assert r.returncode_hint == 0

    def test_hint_uno_cuando_hay_fallos(self):
        """returncode_hint=1 cuando failed > 0."""
        f = TestFailure(test_class="T", method="m", kind="FAIL", message="", traceback="")
        r = TestResult(total=1, passed=0, failed=1, errors=0, failures=[f])
        assert r.returncode_hint == 1

    def test_hint_uno_cuando_parse_falla(self):
        """returncode_hint=1 cuando parse_failed=True."""
        r = TestResult(parse_failed=True)
        assert r.returncode_hint == 1


# ---------------------------------------------------------------------------
# Test — Fixture G: Odoo v19 format (xfail — no confirmed v19 fixture yet)
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    reason="D3: formato v19 FAILED (failures=N, errors=M) pendiente confirmacion con fixture real",
    strict=False,
)
def test_fixture_g_v19_format():
    """Fixture G (xfail D3): parsea formato v19 'FAILED (failures=1, errors=0)'."""
    result = parse_odoo_test_output(FIXTURE_G_V19.splitlines(keepends=True))
    # Si llega aca: el regex cubre v19, marcar como xpass (D3 resuelto)
    assert result.parse_failed is False
    assert result.failed == 1
    assert result.errors == 0
    assert result.total == 3
