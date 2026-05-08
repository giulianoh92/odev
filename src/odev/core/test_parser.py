"""Parser de salida de tests de Odoo.

Convierte la salida de texto del test runner de Odoo en estructuras de datos
tipadas, permitiendo consumo programatico por agentes IA, CI pipelines y
modos de salida filtrados.

Soporta formatos Odoo v14-v18. Formato v19 en espera de fixture confirmado.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Literal

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
RE_RESULT_FAILED = re.compile(
    r"FAILED\s*\((?:failures=(\d+))?(?:,\s*)?(?:errors=(\d+))?\)"
)

# Separadores de bloque: "======" o "------" (5+ caracteres)
RE_SEPARATOR = re.compile(r"^[=\-]{5,}\s*$")


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TestFailure:
    """Representa un test fallido o con error.

    Campos:
        test_class: Nombre de la clase de test.
        method:     Nombre del metodo de test.
        kind:       'FAIL' para assertion failures, 'ERROR' para excepciones.
        message:    Primera linea del traceback (puede estar vacia).
        traceback:  Contenido completo del traceback capturado.
    """

    test_class: str
    method: str
    kind: Literal["FAIL", "ERROR"]
    message: str
    traceback: str


@dataclass
class TestResult:
    """Resultado completo de una corrida de tests Odoo.

    Campos:
        total:        Total de tests ejecutados (de 'Ran N tests').
        passed:       Tests exitosos (= total - failed - errors).
        failed:       Tests con assertion failure.
        errors:       Tests con excepcion no capturada.
        duration:     Duracion total en segundos.
        failures:     Lista de TestFailure con detalles de cada fallo/error.
        parse_failed: True si la salida no pudo parsearse (sin linea 'Ran X tests').
        raw_output:   Salida original concatenada (presente cuando parse_failed=True).
    """

    total: int = 0
    passed: int = 0
    failed: int = 0
    errors: int = 0
    duration: float = 0.0
    failures: list[TestFailure] = field(default_factory=list)
    parse_failed: bool = False
    raw_output: str = ""

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
    current_kind: Literal["FAIL", "ERROR"] | None = None
    current_class: str = ""
    current_method: str = ""
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
            current_class = ""
            current_method = ""
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
                # Puede ser nueva cabecera FAIL/ERROR en esta misma linea
                m_fail = RE_FAIL.search(stripped)
                if m_fail:
                    _finalize_current_failure()
                    current_kind = m_fail.group(1)  # type: ignore[assignment]
                    current_class = m_fail.group(2)
                    current_method = m_fail.group(3)
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

    # Si la linea 'Ran X tests' nunca aparecio → fallback a raw output
    if not ran_found:
        raw = "".join(all_lines)
        return TestResult(parse_failed=True, raw_output=raw)

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
    )
