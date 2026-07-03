"""Tests para el filtro de log Odoo usado por los modos compactos.

Cubre la funcion pura filter_odoo_log() que reduce el log crudo de una
corrida `odoo -u/-i ... --stop-after-init` a las lineas relevantes:
WARNING/ERROR/CRITICAL, bloques de traceback completos y la linea final
de exito ("Modules loaded.").
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Fixtures de log de update/install
# ---------------------------------------------------------------------------

_LOG_UPDATE_OK = """\
2026-07-03 10:00:00,001 1 INFO test_db odoo.modules.loading: loading 42 modules...
2026-07-03 10:00:00,100 1 INFO test_db odoo.modules.loading: Loading module sale (40/42)
2026-07-03 10:00:01,000 1 INFO test_db odoo.modules.loading: 42 modules loaded in 1.20s, 0 queries (+0 extra)
2026-07-03 10:00:01,100 1 INFO test_db odoo.modules.loading: Modules loaded.
2026-07-03 10:00:01,200 1 INFO test_db odoo.modules.registry: Registry loaded in 1.500s
"""

_LOG_UPDATE_WARNING = """\
2026-07-03 10:00:00,001 1 INFO test_db odoo.modules.loading: loading 42 modules...
2026-07-03 10:00:00,500 1 WARNING test_db odoo.models: sale.order: inconsistent 'compute_sudo' among fields
2026-07-03 10:00:01,100 1 INFO test_db odoo.modules.loading: Modules loaded.
"""

_LOG_UPDATE_TRACEBACK = """\
2026-07-03 10:00:00,001 1 INFO test_db odoo.modules.loading: loading 42 modules...
2026-07-03 10:00:00,800 1 ERROR test_db odoo.modules.registry: Failed to load registry
Traceback (most recent call last):
  File "/usr/lib/python3/dist-packages/odoo/modules/registry.py", line 90, in new
    odoo.modules.load_modules(registry)
  File "/usr/lib/python3/dist-packages/odoo/addons/my_mod/models/thing.py", line 12, in <module>
    class Thing(models.Model)
SyntaxError: expected ':'
2026-07-03 10:00:00,900 1 INFO test_db odoo.service: Stopping...
"""

_LOG_UPDATE_CRITICAL = """\
2026-07-03 10:00:00,001 1 INFO test_db odoo.modules.loading: loading 42 modules...
2026-07-03 10:00:00,800 1 CRITICAL test_db odoo.modules.module: Couldn't load module ghost_mod
2026-07-03 10:00:00,900 1 INFO test_db odoo.service: Stopping...
"""


def _filtrar(fixture: str):
    from odev.core.odoo_log_filter import filter_odoo_log

    return filter_odoo_log(fixture.splitlines())


# ---------------------------------------------------------------------------
# Log limpio — nada relevante, success line presente
# ---------------------------------------------------------------------------


class TestLogLimpio:
    """Update exitoso: sin lineas relevantes, con linea de exito, hint 0."""

    def test_sin_lineas_relevantes(self) -> None:
        """Log limpio → relevant_lines vacio (INFO no es relevante)."""
        resultado = _filtrar(_LOG_UPDATE_OK)
        assert resultado.relevant_lines == []

    def test_success_line_detectada(self) -> None:
        """Log limpio → success_line contiene 'Modules loaded.'."""
        resultado = _filtrar(_LOG_UPDATE_OK)
        assert resultado.success_line is not None
        assert "Modules loaded." in resultado.success_line

    def test_hint_cero(self) -> None:
        """Log limpio → returncode_hint 0."""
        resultado = _filtrar(_LOG_UPDATE_OK)
        assert resultado.returncode_hint == 0


# ---------------------------------------------------------------------------
# Log con WARNING — visible pero no falla
# ---------------------------------------------------------------------------


class TestLogConWarning:
    """WARNING aparece en relevant_lines pero no cambia el hint."""

    def test_warning_en_relevant_lines(self) -> None:
        """La linea WARNING completa aparece en relevant_lines."""
        resultado = _filtrar(_LOG_UPDATE_WARNING)
        assert len(resultado.relevant_lines) == 1
        assert "WARNING" in resultado.relevant_lines[0]
        assert "compute_sudo" in resultado.relevant_lines[0]

    def test_warning_no_cambia_hint(self) -> None:
        """WARNING solo → returncode_hint sigue 0."""
        resultado = _filtrar(_LOG_UPDATE_WARNING)
        assert resultado.returncode_hint == 0
        assert resultado.has_traceback is False
        assert resultado.has_critical is False


# ---------------------------------------------------------------------------
# Log con Traceback — bloque completo + hint 1
# ---------------------------------------------------------------------------


class TestLogConTraceback:
    """Traceback: bloque completo capturado, has_traceback True, hint 1."""

    def test_traceback_detectado(self) -> None:
        resultado = _filtrar(_LOG_UPDATE_TRACEBACK)
        assert resultado.has_traceback is True

    def test_bloque_traceback_completo(self) -> None:
        """El bloque incluye desde 'Traceback' hasta la excepcion final."""
        resultado = _filtrar(_LOG_UPDATE_TRACEBACK)
        contenido = "\n".join(resultado.relevant_lines)
        assert "Traceback (most recent call last):" in contenido
        assert "SyntaxError: expected ':'" in contenido
        # La linea ERROR que precede al traceback tambien es relevante
        assert "Failed to load registry" in contenido

    def test_bloque_traceback_corta_en_siguiente_timestamp(self) -> None:
        """La linea INFO posterior al traceback NO entra en relevant_lines."""
        resultado = _filtrar(_LOG_UPDATE_TRACEBACK)
        contenido = "\n".join(resultado.relevant_lines)
        assert "Stopping..." not in contenido

    def test_hint_uno(self) -> None:
        """Traceback → returncode_hint 1 aunque el proceso salga con 0."""
        resultado = _filtrar(_LOG_UPDATE_TRACEBACK)
        assert resultado.returncode_hint == 1

    def test_sin_success_line(self) -> None:
        """Update fallido → success_line None (no llego a 'Modules loaded.')."""
        resultado = _filtrar(_LOG_UPDATE_TRACEBACK)
        assert resultado.success_line is None


# ---------------------------------------------------------------------------
# Log con CRITICAL — hint 1
# ---------------------------------------------------------------------------


class TestLogConCritical:
    """CRITICAL: linea relevante, has_critical True, hint 1."""

    def test_critical_detectado(self) -> None:
        resultado = _filtrar(_LOG_UPDATE_CRITICAL)
        assert resultado.has_critical is True
        assert resultado.returncode_hint == 1

    def test_critical_en_relevant_lines(self) -> None:
        resultado = _filtrar(_LOG_UPDATE_CRITICAL)
        contenido = "\n".join(resultado.relevant_lines)
        assert "Couldn't load module ghost_mod" in contenido
