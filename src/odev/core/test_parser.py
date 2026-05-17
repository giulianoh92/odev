"""Parser de salida de tests de Odoo.

Convierte la salida de texto del test runner de Odoo en estructuras de datos
tipadas, permitiendo consumo programatico por agentes IA, CI pipelines y
modos de salida filtrados.

Soporta formatos Odoo v14-v18 y v19 (dos pasadas).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Literal, Optional

# ---------------------------------------------------------------------------
# Regex compilados al nivel de modulo (no dentro de funciones)
# ---------------------------------------------------------------------------

# Prefijo de timestamp en logs Odoo: "2024-01-15 10:00:00,001 1234 LEVEL ..."
RE_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}\s")

# Cabecera de fallo/error: "FAIL: TestClass.method" o "ERROR: TestClass.method"
# Aparece dentro de una linea de log: "... FAIL: TestSaleOrder.test_create"
RE_FAIL = re.compile(r"\b(FAIL|ERROR):\s+(\w+)\.(\w+)")

# Linea de resumen: "Ran 6 tests in 0.500s" o "Ran 1 test in 0.001s"
RE_RAN = re.compile(r"Ran (\d+) tests? in ([\d.]+)s")

# Resultado exitoso: linea "OK" sola (despues de RE_RAN)
RE_RESULT_OK = re.compile(r"^\s*OK\s*$")

# Resultado fallido: "FAILED (failures=N)" o "FAILED (errors=N)" o ambos
RE_RESULT_FAILED = re.compile(r"FAILED\s*\((?:failures=(\d+))?(?:,\s*)?(?:errors=(\d+))?\)")

# Separadores de bloque: "======" o "------" (5+ caracteres)
RE_SEPARATOR = re.compile(r"^[=\-]{5,}\s*$")

# Odoo v19: linea de resumen "N failed, M error(s) of T tests when loading database 'db'"
RE_ODOO19_SUMMARY = re.compile(
    r"(\d+) failed, (\d+) error\(s\) of (\d+) tests when loading database"
)

# Odoo v19: linea de duracion "odoo.tests.stats: <module>: N tests X.Xs Q queries"
RE_ODOO19_DURATION = re.compile(r"odoo\.tests\.stats:\s+\S+:\s+(\d+) tests ([\d.]+)s (\d+) queries")

# Cabecera setUpClass: "ERROR: setUpClass (odoo.addons.mod.tests.file.Class)"
RE_FAIL_SETUP = re.compile(r"\b(FAIL|ERROR):\s+setUpClass\s+\(([\w.]+)\)")

# Inicio de traceback bare (sin cabecera FAIL/ERROR previa)
RE_TRACEBACK_START = re.compile(r"Traceback \(most recent call last\):")


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TestFailure:
    """Representa un test fallido o con error.

    Campos:
        test_class: Nombre de la clase de test (None para LOADING_ERROR).
        method:     Nombre del metodo de test (None para LOADING_ERROR).
        kind:       'FAIL', 'ERROR' o 'LOADING_ERROR'.
        message:    Primera linea del traceback (puede estar vacia).
        traceback:  Contenido completo del traceback capturado.
    """

    test_class: Optional[str] = None
    method: Optional[str] = None
    kind: Literal["FAIL", "ERROR", "LOADING_ERROR"] = "FAIL"
    message: str = ""
    traceback: str = ""


@dataclass
class TestResult:
    """Resultado completo de una corrida de tests Odoo.

    Campos:
        total:               Total de tests ejecutados.
        passed:              Tests exitosos (= total - failed - errors).
        failed:              Tests con assertion failure.
        errors:              Tests con excepcion no capturada.
        duration:            Duracion total en segundos.
        failures:            Lista de TestFailure con detalles de cada fallo/error.
        parse_failed:        True si la salida no pudo parsearse.
        raw_output:          Salida original concatenada (cuando parse_failed=True).
        raw_summary_line:    Linea de resumen v19 capturada (None en v14-v18).
        fallback_counters_used: True si los contadores vienen del segundo paso v19.
    """

    total: int = 0
    passed: int = 0
    failed: int = 0
    errors: int = 0
    duration: float = 0.0
    failures: list[TestFailure] = field(default_factory=list)
    parse_failed: bool = False
    raw_output: str = ""
    raw_summary_line: Optional[str] = None
    fallback_counters_used: bool = False

    @property
    def returncode_hint(self) -> int:
        """Codigo de salida sugerido segun el resultado.

        Retorna:
            1 si hay fallos, errores o el parseo fallo; 0 en caso contrario.
        """
        return 1 if (self.failed or self.errors or self.parse_failed) else 0


# ---------------------------------------------------------------------------
# Parser principal
# ---------------------------------------------------------------------------

_STATE_SCANNING = "SCANNING"
_STATE_COLLECTING = "COLLECTING"


def parse_odoo_test_output(lines: Iterable[str]) -> TestResult:
    """Parsea la salida de texto del test runner de Odoo.

    Implementa una maquina de estados simple:
      SCANNING → detecta cabeceras FAIL/ERROR, linea 'Ran X tests', resultado
      COLLECTING_TRACEBACK → acumula lineas hasta el proximo timestamp o EOF

    Argumentos:
        lines: Iterable de lineas de texto (con o sin newline al final).
               Acepta list[str], generadores y cualquier Iterable[str].

    Retorna:
        TestResult con todos los campos poblados. Si no se encuentra
        la linea 'Ran X tests', retorna TestResult(parse_failed=True, raw_output=...).
    """
    all_lines: list[str] = list(lines)

    if not all_lines:
        return TestResult(parse_failed=True, raw_output="")

    state = _STATE_SCANNING
    ran_found = False

    total = 0
    duration = 0.0
    failed_count = 0
    errors_count = 0
    failures: list[TestFailure] = []

    # Estado para traceback en curso
    current_kind: Literal["FAIL", "ERROR", "LOADING_ERROR"] | None = None
    current_class: Optional[str] = None
    current_method: Optional[str] = None
    current_tb_lines: list[str] = []

    def _finalize_current_failure() -> None:
        """Cierra el failure/error en curso y lo agrega a la lista."""
        nonlocal current_kind, current_class, current_method, current_tb_lines
        if current_kind is not None:
            tb = "".join(current_tb_lines).rstrip()
            first_line = tb.splitlines()[0] if tb.splitlines() else ""
            failures.append(
                TestFailure(
                    test_class=current_class,
                    method=current_method,
                    kind=current_kind,
                    message=first_line,
                    traceback=tb,
                )
            )
            current_kind = None
            current_class = None
            current_method = None
            current_tb_lines = []

    for line in all_lines:
        stripped = line.rstrip("\n").rstrip("\r")

        if state == _STATE_SCANNING:
            # Detectar cabecera FAIL/ERROR dentro de una linea de log
            m_fail = RE_FAIL.search(stripped)
            if m_fail:
                # Si habia un traceback anterior, cerrarlo
                _finalize_current_failure()
                current_kind = m_fail.group(1)  # type: ignore[assignment]
                current_class = m_fail.group(2)
                current_method = m_fail.group(3)
                current_tb_lines = []
                state = _STATE_COLLECTING
                continue

            # Detectar cabecera setUpClass: "ERROR: setUpClass (mod.path.Class)"
            m_setup = RE_FAIL_SETUP.search(stripped)
            if m_setup:
                _finalize_current_failure()
                current_kind = m_setup.group(1)  # type: ignore[assignment]
                dotted = m_setup.group(2)
                current_class = dotted.rsplit(".", 1)[-1]  # ultimo segmento
                current_method = "setUpClass"
                current_tb_lines = []
                state = _STATE_COLLECTING
                continue

            # Detectar bare traceback (sin cabecera FAIL/ERROR previa)
            if RE_TRACEBACK_START.search(stripped):
                if current_kind is None:  # solo si no hay failure activo
                    _finalize_current_failure()
                    current_kind = "LOADING_ERROR"  # type: ignore[assignment]
                    current_class = None
                    current_method = None
                    current_tb_lines = [line]
                    state = _STATE_COLLECTING
                    continue

            # Detectar linea "Ran N tests in X.Xs"
            m_ran = RE_RAN.search(stripped)
            if m_ran:
                _finalize_current_failure()
                total = int(m_ran.group(1))
                duration = float(m_ran.group(2))
                ran_found = True
                state = _STATE_SCANNING
                continue

        elif state == _STATE_COLLECTING:
            # Boundary: nuevo timestamp o separador → cerrar traceback actual
            if RE_TIMESTAMP.match(stripped):
                # Puede ser nueva cabecera FAIL/ERROR o setUpClass en esta linea
                m_fail = RE_FAIL.search(stripped)
                m_setup = RE_FAIL_SETUP.search(stripped)
                if m_fail:
                    _finalize_current_failure()
                    current_kind = m_fail.group(1)  # type: ignore[assignment]
                    current_class = m_fail.group(2)
                    current_method = m_fail.group(3)
                    current_tb_lines = []
                    # Seguir en COLLECTING
                elif m_setup:
                    _finalize_current_failure()
                    current_kind = m_setup.group(1)  # type: ignore[assignment]
                    dotted = m_setup.group(2)
                    current_class = dotted.rsplit(".", 1)[-1]
                    current_method = "setUpClass"
                    current_tb_lines = []
                    # Seguir en COLLECTING
                else:
                    # Linea de log normal → cierra traceback
                    _finalize_current_failure()
                    state = _STATE_SCANNING
                continue

            if RE_SEPARATOR.match(stripped):
                _finalize_current_failure()
                state = _STATE_SCANNING
                continue

            # Detectar "Ran N tests" desde dentro de COLLECTING (edge case)
            m_ran = RE_RAN.search(stripped)
            if m_ran:
                _finalize_current_failure()
                total = int(m_ran.group(1))
                duration = float(m_ran.group(2))
                ran_found = True
                state = _STATE_SCANNING
                continue

            # Acumular linea al traceback
            current_tb_lines.append(line)

    # Cerrar traceback si quedaba pendiente al llegar al EOF
    _finalize_current_failure()

    # Parsear resultado OK/FAILED de la linea final relevante
    for line in all_lines:
        stripped = line.rstrip("\n").rstrip("\r")
        if RE_RESULT_OK.match(stripped):
            pass  # sin contadores que actualizar
        m_failed = RE_RESULT_FAILED.search(stripped)
        if m_failed:
            failed_count = int(m_failed.group(1) or 0)
            errors_count = int(m_failed.group(2) or 0)

    # Segundo paso: buscar resumen Odoo v19 si la linea 'Ran X tests' no aparecio
    raw_summary_line: Optional[str] = None
    fallback_counters_used = False
    if not ran_found:
        for line in all_lines:
            stripped = line.rstrip("\n").rstrip("\r")
            m19 = RE_ODOO19_SUMMARY.search(stripped)
            if m19:
                failed_count = int(m19.group(1))
                errors_count = int(m19.group(2))
                total = int(m19.group(3))
                raw_summary_line = stripped
                fallback_counters_used = True
                ran_found = True
                break
        if ran_found:
            for line in all_lines:
                stripped = line.rstrip("\n").rstrip("\r")
                m_dur = RE_ODOO19_DURATION.search(stripped)
                if m_dur:
                    duration = float(m_dur.group(2))
                    break

    # Si la linea 'Ran X tests' nunca aparecio → fallback a raw output
    # Nota: se preservan los failures recolectados (setUpClass/LOADING_ERROR)
    if not ran_found:
        raw = "".join(all_lines)
        return TestResult(parse_failed=True, raw_output=raw, failures=failures)

    passed = total - failed_count - errors_count
    return TestResult(
        total=total,
        passed=max(passed, 0),
        failed=failed_count,
        errors=errors_count,
        duration=duration,
        failures=failures,
        parse_failed=False,
        raw_output="",
        raw_summary_line=raw_summary_line,
        fallback_counters_used=fallback_counters_used,
    )
