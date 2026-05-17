"""Tests para odev.core.ports — gestion de puertos para multi-proyecto.

Verifica la deteccion de puertos disponibles y la sugerencia de
conjuntos de puertos libres para proyectos simultaneos. Tambien cubre
allocate_ports (0.4.0): asignacion atomica con verificacion de registro
y PortAllocationError cuando se agotan los offsets.
"""

import socket
import time
import warnings
from pathlib import Path
from unittest.mock import patch

import pytest

from odev.core.ports import CONJUNTOS_PUERTOS, puerto_disponible, sugerir_puertos


class TestPuertoDisponible:
    """Grupo de tests para la funcion puerto_disponible()."""

    def test_retorna_true_para_puerto_libre(self):
        """Retorna True cuando el puerto esta disponible para uso."""
        # Usa un puerto alto poco probable que este en uso
        # Primero encontramos un puerto libre usando el OS
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            puerto_libre = s.getsockname()[1]

        # Ahora que lo cerramos, deberia estar disponible
        assert puerto_disponible(puerto_libre) is True

    def test_retorna_false_para_puerto_ocupado(self):
        """Retorna False cuando el puerto esta ocupado por otro proceso."""
        # Ocupar un puerto temporalmente
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("127.0.0.1", 0))
            puerto_ocupado = s.getsockname()[1]
            # El socket sigue abierto, el puerto esta ocupado
            assert puerto_disponible(puerto_ocupado) is False


class TestSugerirPuertos:
    """Grupo de tests para la funcion sugerir_puertos()."""

    def test_retorna_dict_con_claves_esperadas(self):
        """Retorna un diccionario con las claves de puertos esperadas."""
        resultado = sugerir_puertos()

        claves_esperadas = {"WEB_PORT", "PGWEB_PORT", "DB_PORT", "DEBUGPY_PORT", "MAILHOG_PORT"}
        assert set(resultado.keys()) == claves_esperadas

    def test_retorna_puertos_base_cuando_disponibles(self):
        """Retorna los puertos base cuando todos estan disponibles."""
        # Mockear que todos los puertos estan disponibles
        with patch("odev.core.ports.puerto_disponible", return_value=True):
            resultado = sugerir_puertos()

        assert resultado["WEB_PORT"] == 8069
        assert resultado["PGWEB_PORT"] == 8081
        assert resultado["DB_PORT"] == 5432
        assert resultado["DEBUGPY_PORT"] == 5678
        assert resultado["MAILHOG_PORT"] == 8025

    def test_incrementa_cuando_puertos_base_ocupados(self):
        """Incrementa el offset cuando los puertos base estan ocupados."""
        llamadas = [0]

        def mock_disponible(puerto):
            """Simula que los puertos base estan ocupados pero base+1 estan libres."""
            llamadas[0] += 1
            # Los puertos base (offset 0) estan ocupados
            puertos_base = set(CONJUNTOS_PUERTOS.values())
            if puerto in puertos_base:
                return False
            return True

        with patch("odev.core.ports.puerto_disponible", side_effect=mock_disponible):
            resultado = sugerir_puertos()

        # Deberia haber incrementado en 1
        assert resultado["WEB_PORT"] == 8070
        assert resultado["PGWEB_PORT"] == 8082
        assert resultado["DB_PORT"] == 5433
        assert resultado["DEBUGPY_PORT"] == 5679
        assert resultado["MAILHOG_PORT"] == 8026

    def test_fallback_despues_de_100_intentos(self):
        """Retorna puertos base como fallback si no encuentra disponibles en 100 intentos."""
        with patch("odev.core.ports.puerto_disponible", return_value=False):
            resultado = sugerir_puertos()

        # Fallback: retorna los puertos base sin verificar
        assert resultado == CONJUNTOS_PUERTOS

    def test_valores_son_enteros(self):
        """Todos los valores retornados son enteros."""
        with patch("odev.core.ports.puerto_disponible", return_value=True):
            resultado = sugerir_puertos()

        for clave, valor in resultado.items():
            assert isinstance(valor, int), f"{clave} no es entero: {type(valor)}"


# ── T05 RED: Tests de allocate_ports y PortAllocationError ──


@pytest.fixture
def registry_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Fixture que redirecciona el registro a tmp_path para tests de allocate_ports."""
    import odev.core.registry as reg_mod

    monkeypatch.setattr(reg_mod, "ODEV_HOME", tmp_path)
    monkeypatch.setattr(reg_mod, "REGISTRY_PATH", tmp_path / "registry.yaml")
    monkeypatch.setattr(reg_mod, "PROJECTS_DIR", tmp_path / "projects")
    (tmp_path / "projects").mkdir()
    from odev.core.registry import Registry

    return Registry()


class TestAllocatePorts:
    """Grupo de tests para la funcion allocate_ports()."""

    def test_allocate_ports_skips_registry_claimed_offset(
        self, registry_tmp
    ) -> None:
        """allocate_ports omite offsets cuyos puertos ya estan reclamados en el registro.

        REQ-PA-2 Scenario 1: socket libre pero offset registrado se salta.
        """
        from odev.core.ports import allocate_ports

        # Pre-reclamar offset 0 (puertos base)
        registry_tmp.asignar_puertos("proyecto-existente", CONJUNTOS_PUERTOS.copy())

        # Mockear todos los sockets como libres para aislar la logica de registro
        with patch("odev.core.ports.puerto_disponible", return_value=True):
            resultado = allocate_ports("nuevo-proyecto", registry_tmp)

        # El resultado no debe coincidir con los puertos base (offset 0)
        assert resultado["WEB_PORT"] != CONJUNTOS_PUERTOS["WEB_PORT"]

    def test_allocate_ports_persists_claim_in_registry(
        self, registry_tmp
    ) -> None:
        """allocate_ports escribe la asignacion en el registro antes de retornar.

        REQ-PA-1: La reclamacion es atomica — el registro contiene la entrada
        antes de que el wizard continue.
        """
        from odev.core.ports import allocate_ports

        with patch("odev.core.ports.puerto_disponible", return_value=True):
            resultado = allocate_ports("mi-proyecto", registry_tmp)

        entry = registry_tmp.obtener("mi-proyecto")
        assert entry is not None
        assert entry.ports == resultado

    def test_allocate_ports_raises_after_100_offsets(
        self, registry_tmp
    ) -> None:
        """allocate_ports lanza PortAllocationError cuando se agotan los 100 offsets."""
        from odev.core.ports import PortAllocationError, allocate_ports

        # Todos los sockets ocupados
        with patch("odev.core.ports.puerto_disponible", return_value=False):
            with pytest.raises(PortAllocationError):
                allocate_ports("sin-puertos", registry_tmp)

    def test_allocate_ports_lock_under_50ms(self, registry_tmp) -> None:
        """La operacion completa de allocate_ports dura menos de 50ms.

        NF-1: El lock no se sostiene durante el wizard.
        """
        from odev.core.ports import allocate_ports

        with patch("odev.core.ports.puerto_disponible", return_value=True):
            inicio = time.perf_counter()
            allocate_ports("rapido", registry_tmp)
            duracion_ms = (time.perf_counter() - inicio) * 1000

        assert duracion_ms < 50, f"allocate_ports tardo {duracion_ms:.1f}ms (limite: 50ms)"

    def test_sugerir_puertos_emits_deprecation_warning(self) -> None:
        """sugerir_puertos emite DeprecationWarning al ser llamada.

        backward-compat: se conserva la funcion pero avisa que esta deprecada.
        """
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            with patch("odev.core.ports.puerto_disponible", return_value=True):
                sugerir_puertos()

        deprecation_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
        assert len(deprecation_warnings) >= 1, "Se esperaba al menos un DeprecationWarning"


# ── T12 RED: PORT_KEYS debe existir como tupla derivada de CONJUNTOS_PUERTOS ──


class TestPortKeys:
    """Verifica que PORT_KEYS es una constante publica en core/ports.py (Q10).

    T12.1 RED: el test falla hasta que se defina PORT_KEYS en ports.py.
    """

    def test_port_keys_exportada(self):
        """PORT_KEYS se puede importar desde odev.core.ports."""
        from odev.core.ports import PORT_KEYS  # noqa: F401 — solo verifica importabilidad

    def test_port_keys_es_tupla(self):
        """PORT_KEYS es una tupla de strings."""
        from odev.core.ports import PORT_KEYS

        assert isinstance(PORT_KEYS, tuple), "PORT_KEYS debe ser una tupla"
        assert all(isinstance(k, str) for k in PORT_KEYS), (
            "Todos los elementos de PORT_KEYS deben ser strings"
        )

    def test_port_keys_coincide_con_conjuntos_puertos(self):
        """PORT_KEYS es igual a tuple(CONJUNTOS_PUERTOS.keys()).

        Esto garantiza una unica fuente de verdad para las claves de puertos.
        """
        from odev.core.ports import PORT_KEYS

        esperado = tuple(CONJUNTOS_PUERTOS.keys())
        assert PORT_KEYS == esperado, (
            f"PORT_KEYS {PORT_KEYS} debe ser igual a tuple(CONJUNTOS_PUERTOS.keys()) {esperado}"
        )

    def test_port_keys_contiene_claves_esperadas(self):
        """PORT_KEYS contiene las claves canonicas de puertos."""
        from odev.core.ports import PORT_KEYS

        claves_esperadas = {"WEB_PORT", "PGWEB_PORT", "DB_PORT", "DEBUGPY_PORT", "MAILHOG_PORT"}
        assert set(PORT_KEYS) == claves_esperadas, (
            f"PORT_KEYS debe contener exactamente {claves_esperadas}"
        )
