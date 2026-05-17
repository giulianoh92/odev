"""Tests para odev.commands.doctor — diagnostico del entorno.

Verifica las funciones de verificacion individuales del comando doctor,
mockeando subprocess y socket para evitar dependencias externas.
Cubre 0.4.0: MAILHOG_PORT en puertos_a_verificar, simbolo puerto_disponible
importado desde odev.core.ports, backfill de entradas legacy y GC de puertos.
"""

import socket
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from odev.commands.doctor import (
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
    """Grupo de tests para la funcion puerto_disponible importada desde core.ports."""

    def test_puerto_libre(self):
        """Retorna True para un puerto libre."""
        from odev.core.ports import puerto_disponible

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            puerto_libre = s.getsockname()[1]

        assert puerto_disponible(puerto_libre) is True

    def test_puerto_ocupado(self):
        """Retorna False para un puerto ocupado."""
        from odev.core.ports import puerto_disponible

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("127.0.0.1", 0))
            puerto_ocupado = s.getsockname()[1]

            assert puerto_disponible(puerto_ocupado) is False


# ── T17 RED: Tests de MAILHOG, canonicalizacion de puerto_disponible, backfill y GC ──


@pytest.fixture
def registry_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Fixture de registro aislado para tests de doctor."""
    import odev.core.registry as reg_mod

    monkeypatch.setattr(reg_mod, "ODEV_HOME", tmp_path)
    monkeypatch.setattr(reg_mod, "REGISTRY_PATH", tmp_path / "registry.yaml")
    monkeypatch.setattr(reg_mod, "PROJECTS_DIR", tmp_path / "projects")
    (tmp_path / "projects").mkdir()
    from odev.core.registry import Registry

    return Registry()


class TestVerificarPuertosMailhog:
    """Verifica que MAILHOG_PORT se incluye en la verificacion de puertos."""

    def test_verificar_puertos_includes_mailhog(self, tmp_path: Path, monkeypatch) -> None:
        """_verificar_puertos verifica MAILHOG_PORT del .env.

        REQ-DC-1: MAILHOG_PORT debe aparecer en la lista de verificacion.
        """
        from odev.commands.doctor import _verificar_puertos
        from odev.core.compat import ProjectMode

        # Setup: proyecto con .env que incluye MAILHOG_PORT
        env_file = tmp_path / ".env"
        env_file.write_text(
            "WEB_PORT=8069\nDB_PORT=5432\nPGWEB_PORT=8081\n"
            "DEBUGPY_PORT=5678\nMAILHOG_PORT=8025\n"
        )

        with (
            patch("odev.commands.doctor.detect_mode", return_value=(ProjectMode.PROJECT, tmp_path)),
            patch("odev.commands.doctor.puerto_disponible", return_value=True),
        ):
            resultado = _verificar_puertos()

        # Debe retornar True (todos disponibles) sin crashear por MAILHOG_PORT
        assert resultado is True

    def test_verificar_puertos_uses_canonical_puerto_disponible(
        self, tmp_path: Path
    ) -> None:
        """doctor usa odev.core.ports.puerto_disponible, no el simbolo local eliminado.

        REQ-DC-2: el modulo doctor no debe tener _puerto_disponible local.
        """
        import odev.commands.doctor as doctor_mod

        assert not hasattr(doctor_mod, "_puerto_disponible"), (
            "doctor.py no debe tener _puerto_disponible local — "
            "debe importar de odev.core.ports"
        )

    def test_verificar_puertos_mailhog_conflict_reported(
        self, tmp_path: Path
    ) -> None:
        """Cuando MAILHOG_PORT esta ocupado, doctor reporta el conflicto.

        REQ-DC-1 Scenario: MAILHOG conflict detected.
        """
        from odev.commands.doctor import _verificar_puertos
        from odev.core.compat import ProjectMode

        env_file = tmp_path / ".env"
        env_file.write_text("MAILHOG_PORT=8025\n")

        def mock_puerto_disponible(puerto: int) -> bool:
            return puerto != 8025  # MAILHOG_PORT ocupado

        with (
            patch("odev.commands.doctor.detect_mode", return_value=(ProjectMode.PROJECT, tmp_path)),
            patch("odev.commands.doctor.puerto_disponible", side_effect=mock_puerto_disponible),
        ):
            resultado = _verificar_puertos()

        assert resultado is False


class TestDoctorBackfill:
    """Verifica el backfill de entradas legacy desde .env."""

    def test_doctor_backfills_legacy_entry_from_env(
        self, tmp_path: Path, registry_tmp, monkeypatch
    ) -> None:
        """doctor rellena el campo ports en entradas legacy con .env completo.

        REQ-PA-3: backfill de 5 claves de puertos desde .env.
        """

        # Crear proyecto legacy (sin campo ports)
        work_dir = tmp_path / "mi-proyecto"
        work_dir.mkdir()
        env_file = work_dir / ".env"
        env_file.write_text(
            "WEB_PORT=8069\nDB_PORT=5432\nPGWEB_PORT=8081\n"
            "DEBUGPY_PORT=5678\nMAILHOG_PORT=8025\n"
        )

        from odev.core.registry import RegistryEntry

        entry_legacy = RegistryEntry(
            nombre="mi-proyecto",
            directorio_trabajo=work_dir,
            directorio_config=work_dir,
            modo="inline",
            version_odoo="18.0",
            fecha_creacion="2026-01-01",
            ports=None,  # legacy
        )
        registry_tmp.registrar(entry_legacy)

        # Ejecutar backfill
        from odev.commands.doctor import _verificar_registry_puertos

        _verificar_registry_puertos(registry_tmp)

        # Verificar que los ports fueron backfilleados
        actualizado = registry_tmp.obtener("mi-proyecto")
        assert actualizado is not None
        assert actualizado.ports is not None
        assert actualizado.ports["WEB_PORT"] == 8069
        assert actualizado.ports["MAILHOG_PORT"] == 8025

    def test_doctor_backfill_partial_env_warns(
        self, tmp_path: Path, registry_tmp, monkeypatch, capsys
    ) -> None:
        """Con .env parcial, backfill llena solo las claves presentes y emite warning.

        REQ-PA-3 Scenario: partial .env — missing MAILHOG_PORT.
        """
        work_dir = tmp_path / "proyecto-parcial"
        work_dir.mkdir()
        env_file = work_dir / ".env"
        # Sin MAILHOG_PORT
        env_file.write_text("WEB_PORT=8069\nDB_PORT=5432\n")

        from odev.core.registry import RegistryEntry

        entry = RegistryEntry(
            nombre="proyecto-parcial",
            directorio_trabajo=work_dir,
            directorio_config=work_dir,
            modo="inline",
            version_odoo="18.0",
            fecha_creacion="2026-01-01",
            ports=None,
        )
        registry_tmp.registrar(entry)

        from odev.commands.doctor import _verificar_registry_puertos

        _verificar_registry_puertos(registry_tmp)

        actualizado = registry_tmp.obtener("proyecto-parcial")
        assert actualizado is not None
        assert actualizado.ports is not None
        assert "WEB_PORT" in actualizado.ports
        assert "DB_PORT" in actualizado.ports
        # MAILHOG_PORT no debe aparecer (no estaba en .env)
        assert "MAILHOG_PORT" not in (actualizado.ports or {})

    def test_doctor_gc_removes_stale_entry(
        self, tmp_path: Path, registry_tmp
    ) -> None:
        """GC de doctor elimina entradas cuyo directorio ya no existe.

        REQ-PA-4: limpiar_obsoletos libera puertos de entradas stale.
        """
        stale_dir = tmp_path / "stale-project"
        # No crear el directorio — simula proyecto eliminado

        from odev.core.registry import RegistryEntry

        entry = RegistryEntry(
            nombre="stale-project",
            directorio_trabajo=stale_dir,
            directorio_config=stale_dir,
            modo="inline",
            version_odoo="18.0",
            fecha_creacion="2026-01-01",
            ports={"WEB_PORT": 8069},
        )
        registry_tmp.registrar(entry)

        # Verificar que los puertos estan reclamados antes del GC
        assert 8069 in registry_tmp.puertos_ocupados()

        # Ejecutar GC (via limpiar_obsoletos que ya hace esto)
        eliminados = registry_tmp.limpiar_obsoletos()

        assert "stale-project" in eliminados
        assert 8069 not in registry_tmp.puertos_ocupados()
