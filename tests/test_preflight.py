"""Tests para odev.core.preflight — verificacion de puertos antes de docker compose up.

Verifica REQ-UP-1 y REQ-UP-2: clasificacion de puertos libres, propios
(contenedores del mismo proyecto) y foraneos (otros procesos o proyectos).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from odev.core.preflight import (
    PortStatus,
    PreflightResult,
    classify_bound_port,
    verificar_puertos_pre_up,
)
from odev.core.registry import Registry


@pytest.fixture
def registry_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Registry:
    """Fixture de registro aislado para tests de preflight."""
    import odev.core.registry as reg_mod

    monkeypatch.setattr(reg_mod, "ODEV_HOME", tmp_path)
    monkeypatch.setattr(reg_mod, "REGISTRY_PATH", tmp_path / "registry.yaml")
    monkeypatch.setattr(reg_mod, "PROJECTS_DIR", tmp_path / "projects")
    (tmp_path / "projects").mkdir()
    return Registry()


def _mock_contexto(nombre: str) -> MagicMock:
    """Helper para crear un mock de ProjectContext."""
    ctx = MagicMock()
    ctx.nombre = nombre
    return ctx


def _mock_dc(contenedores: list[dict]) -> MagicMock:
    """Helper para crear un mock de DockerCompose con ps_parsed dado."""
    dc = MagicMock()
    dc.ps_parsed.return_value = contenedores
    return dc


class TestPortStatus:
    """Verifica la dataclass PortStatus."""

    def test_port_status_attributes(self) -> None:
        """PortStatus tiene los atributos nombre, puerto, estado, propietario."""
        ps = PortStatus(
            nombre="WEB_PORT",
            puerto=8069,
            estado="free",
            propietario=None,
        )

        assert ps.nombre == "WEB_PORT"
        assert ps.puerto == 8069
        assert ps.estado == "free"
        assert ps.propietario is None


class TestPreflightResult:
    """Verifica la dataclass PreflightResult y sus propiedades."""

    def test_has_fail_false_when_no_foreign(self) -> None:
        """has_fail es False cuando no hay puertos foreign."""
        result = PreflightResult(statuses=[
            PortStatus("WEB_PORT", 8069, "free", None),
            PortStatus("DB_PORT", 5432, "own_running", "my-project"),
        ])

        assert result.has_fail is False

    def test_has_fail_true_when_foreign_present(self) -> None:
        """has_fail es True cuando hay al menos un puerto foreign."""
        result = PreflightResult(statuses=[
            PortStatus("WEB_PORT", 8069, "foreign_known", "otro-proyecto"),
        ])

        assert result.has_fail is True

    def test_preflight_result_has_fail_property(self) -> None:
        """PreflightResult expone la propiedad has_fail correctamente."""
        result_sin_fallos = PreflightResult(statuses=[
            PortStatus("WEB_PORT", 8069, "free", None),
        ])
        result_con_fallos = PreflightResult(statuses=[
            PortStatus("WEB_PORT", 8069, "foreign_unknown", None),
        ])

        assert result_sin_fallos.has_fail is False
        assert result_con_fallos.has_fail is True

    def test_warns_returns_own_running_statuses(self) -> None:
        """warnings retorna solo los PortStatus con estado own_running."""
        result = PreflightResult(statuses=[
            PortStatus("WEB_PORT", 8069, "free", None),
            PortStatus("DB_PORT", 5432, "own_running", "my-project"),
            PortStatus("PGWEB_PORT", 8081, "foreign_known", "otro"),
        ])

        warns = result.warnings
        assert len(warns) == 1
        assert warns[0].estado == "own_running"

    def test_fails_returns_foreign_statuses(self) -> None:
        """fails retorna PortStatus con estados foreign_known y foreign_unknown."""
        result = PreflightResult(statuses=[
            PortStatus("WEB_PORT", 8069, "free", None),
            PortStatus("DB_PORT", 5432, "foreign_known", "otro"),
            PortStatus("PGWEB_PORT", 8081, "foreign_unknown", None),
        ])

        fails = result.fails
        assert len(fails) == 2


class TestVerificarPuertosPreUp:
    """Verifica la funcion verificar_puertos_pre_up()."""

    def test_all_ports_free_returns_free_status(
        self, registry_tmp: Registry
    ) -> None:
        """Cuando todos los puertos estan libres, retorna estado free para cada uno.

        REQ-UP-1 Scenario 1: all ports free -> preflight pass.
        """
        contexto = _mock_contexto("mi-proyecto")
        dc = _mock_dc([])
        puertos = {"WEB_PORT": 8069, "DB_PORT": 5432}

        with patch("odev.core.preflight.puerto_disponible", return_value=True):
            resultado = verificar_puertos_pre_up(contexto, dc, registry_tmp, puertos)

        assert resultado.has_fail is False
        for status in resultado.statuses:
            assert status.estado == "free"

    def test_own_container_running_classifies_own_running(
        self, registry_tmp: Registry
    ) -> None:
        """Puerto ocupado por contenedor propio se clasifica como own_running.

        REQ-UP-2 Scenario 1: own project already running -> WARN, no fail.
        """
        contexto = _mock_contexto("mi-proyecto")
        # Simular que el contenedor propio tiene WEB_PORT=8069 publicado
        contenedores = [
            {
                "Service": "web",
                "State": "running",
                "Publishers": [{"PublishedPort": 8069, "URL": "0.0.0.0"}],
                "Labels": {"com.docker.compose.project": "mi-proyecto"},
            }
        ]
        dc = _mock_dc(contenedores)
        puertos = {"WEB_PORT": 8069}

        with patch("odev.core.preflight.puerto_disponible", return_value=False):
            resultado = verificar_puertos_pre_up(
                contexto, dc, registry_tmp, puertos
            )

        assert resultado.has_fail is False
        assert resultado.statuses[0].estado == "own_running"

    def test_foreign_process_classifies_foreign_unknown(
        self, registry_tmp: Registry
    ) -> None:
        """Puerto ocupado por proceso ajeno sin registro se clasifica como foreign_unknown.

        REQ-UP-2: foreign process with no registry owner.
        """
        contexto = _mock_contexto("mi-proyecto")
        dc = _mock_dc([])  # sin contenedores propios
        puertos = {"WEB_PORT": 8069}

        with patch("odev.core.preflight.puerto_disponible", return_value=False):
            resultado = verificar_puertos_pre_up(
                contexto, dc, registry_tmp, puertos
            )

        assert resultado.has_fail is True
        assert resultado.statuses[0].estado == "foreign_unknown"

    def test_foreign_port_with_registry_owner_classifies_foreign_known(
        self, registry_tmp: Registry
    ) -> None:
        """Puerto en registro de otro proyecto se clasifica como foreign_known.

        REQ-UP-2 Scenario 2: foreign project's container on port.
        """
        # Registrar otro proyecto con ese puerto
        registry_tmp.asignar_puertos("otro-proyecto", {"WEB_PORT": 8069})

        contexto = _mock_contexto("mi-proyecto")
        dc = _mock_dc([])
        puertos = {"WEB_PORT": 8069}

        with patch("odev.core.preflight.puerto_disponible", return_value=False):
            resultado = verificar_puertos_pre_up(
                contexto, dc, registry_tmp, puertos
            )

        assert resultado.has_fail is True
        status = resultado.statuses[0]
        assert status.estado == "foreign_known"
        assert status.propietario == "otro-proyecto"


class TestClassifyBoundPort:
    """Verifica la funcion classify_bound_port()."""

    def test_classify_own_container(self, registry_tmp: Registry) -> None:
        """Puerto de contenedor propio se clasifica como own_running."""
        contenedores = [
            {
                "Service": "web",
                "Publishers": [{"PublishedPort": 8069}],
                "Labels": {"com.docker.compose.project": "mi-proyecto"},
            }
        ]
        dc = _mock_dc(contenedores)
        contexto = _mock_contexto("mi-proyecto")

        estado, propietario = classify_bound_port(
            8069, "mi-proyecto", dc, registry_tmp
        )

        assert estado == "own_running"
        assert propietario == "mi-proyecto"

    def test_classify_foreign_unknown(self, registry_tmp: Registry) -> None:
        """Puerto sin contenedores ni registro se clasifica como foreign_unknown."""
        dc = _mock_dc([])
        contexto = _mock_contexto("mi-proyecto")

        estado, propietario = classify_bound_port(
            8069, "mi-proyecto", dc, registry_tmp
        )

        assert estado == "foreign_unknown"
        assert propietario is None
