"""Tests para odev.commands.doctor — diagnostico del entorno.

Verifica las funciones de verificacion individuales del comando doctor,
mockeando subprocess y socket para evitar dependencias externas.
"""

import socket
from unittest.mock import MagicMock, patch

import pytest

from odev.commands.doctor import (
    _puerto_disponible,
    _verificar_docker,
    _verificar_docker_compose,
    _verificar_python,
)


class TestVerificarDocker:
    """Grupo de tests para la verificacion de Docker."""

    def test_docker_disponible(self):
        """Retorna True cuando Docker esta instalado y responde."""
        with (
            patch("shutil.which", return_value="/usr/bin/docker"),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="Docker version 24.0.7, build afdd53b",
            )

            resultado = _verificar_docker()

        assert resultado is True

    def test_docker_no_instalado(self):
        """Retorna False cuando Docker no esta instalado."""
        with patch("shutil.which", return_value=None):
            resultado = _verificar_docker()

        assert resultado is False

    def test_docker_instalado_pero_no_responde(self):
        """Retorna False cuando Docker esta instalado pero no responde."""
        with (
            patch("shutil.which", return_value="/usr/bin/docker"),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(returncode=1, stdout="")

            resultado = _verificar_docker()

        assert resultado is False

    def test_docker_timeout(self):
        """Retorna False cuando Docker tarda demasiado en responder."""
        import subprocess

        with (
            patch("shutil.which", return_value="/usr/bin/docker"),
            patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="docker", timeout=10)),
        ):
            resultado = _verificar_docker()

        assert resultado is False


class TestVerificarDockerCompose:
    """Grupo de tests para la verificacion de Docker Compose v2."""

    def test_compose_v2_disponible(self):
        """Retorna True cuando Docker Compose v2 esta disponible."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="Docker Compose version v2.21.0",
            )

            resultado = _verificar_docker_compose()

        assert resultado is True

    def test_compose_v2_no_disponible(self):
        """Retorna False cuando Docker Compose v2 no esta disponible."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="")

            resultado = _verificar_docker_compose()

        assert resultado is False

    def test_compose_file_not_found(self):
        """Retorna False cuando docker no esta en el PATH."""
        with patch("subprocess.run", side_effect=FileNotFoundError):
            resultado = _verificar_docker_compose()

        assert resultado is False


class TestVerificarPython:
    """Grupo de tests para la verificacion de Python."""

    def test_python_version_adecuada(self):
        """Retorna True con Python 3.10+."""
        with (
            patch("platform.python_version", return_value="3.12.0"),
            patch("odev.commands.doctor.sys") as mock_sys,
        ):
            mock_sys.version_info = (3, 12, 0)

            resultado = _verificar_python()

        assert resultado is True

    def test_python_version_antigua(self):
        """Retorna False con Python menor a 3.10."""
        with (
            patch("platform.python_version", return_value="3.8.10"),
            patch("odev.commands.doctor.sys") as mock_sys,
        ):
            mock_sys.version_info = (3, 8, 10)

            resultado = _verificar_python()

        assert resultado is False


class TestPuertoDisponibleDoctor:
    """Grupo de tests para la funcion _puerto_disponible del modulo doctor."""

    def test_puerto_libre(self):
        """Retorna True para un puerto libre."""
        # Encontrar un puerto libre usando el OS
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            puerto_libre = s.getsockname()[1]

        assert _puerto_disponible(puerto_libre) is True

    def test_puerto_ocupado(self):
        """Retorna False para un puerto ocupado."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("127.0.0.1", 0))
            puerto_ocupado = s.getsockname()[1]

            assert _puerto_disponible(puerto_ocupado) is False
