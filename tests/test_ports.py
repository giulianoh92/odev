"""Tests para odev.core.ports — gestion de puertos para multi-proyecto.

Verifica la deteccion de puertos disponibles y la sugerencia de
conjuntos de puertos libres para proyectos simultaneos.
"""

import socket
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

        claves_esperadas = {"WEB_PORT", "PGWEB_PORT", "DB_PORT", "DEBUGPY_PORT"}
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
