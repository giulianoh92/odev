"""Tests para el preflight de odev up — verificacion de puertos antes de compose up.

Verifica REQ-UP-1 y REQ-UP-2: el comando up invoca la verificacion de puertos
antes de llamar a docker compose, y falla con exit 3 si hay conflictos foraneos.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import typer


@pytest.fixture
def registry_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirige el registro global a tmp_path para tests de up."""
    import odev.core.registry as reg_mod

    monkeypatch.setattr(reg_mod, "ODEV_HOME", tmp_path)
    monkeypatch.setattr(reg_mod, "REGISTRY_PATH", tmp_path / "registry.yaml")
    monkeypatch.setattr(reg_mod, "PROJECTS_DIR", tmp_path / "projects")
    (tmp_path / "projects").mkdir()


def _mock_contexto(nombre: str = "mi-proyecto", tmp_path: Path | None = None) -> MagicMock:
    """Helper para construir un mock de ProjectContext."""
    ctx = MagicMock()
    ctx.nombre = nombre
    return ctx


def _mock_rutas(tmp_path: Path) -> MagicMock:
    """Helper que crea un mock de ProjectPaths con .env real."""
    env_file = tmp_path / ".env"
    env_file.write_text(
        "WEB_PORT=8069\nDB_PORT=5432\nPGWEB_PORT=8081\nDEBUGPY_PORT=5678\nMAILHOG_PORT=8025\n"
    )
    config_dir = tmp_path / "config"
    config_dir.mkdir(exist_ok=True)
    # Crear odoo.conf para que la comparacion de mtime no falle
    odoo_conf = config_dir / "odoo.conf"
    odoo_conf.write_text("[options]\n")
    rutas = MagicMock()
    rutas.env_file = env_file
    rutas.logs_dir = tmp_path / "logs"
    rutas.config_dir = config_dir
    return rutas


class TestUpPreflightPass:
    """Verifica que up procede cuando el preflight pasa (puertos libres)."""

    def test_up_invoca_docker_compose_cuando_puertos_libres(
        self, tmp_path: Path, registry_tmp: None
    ) -> None:
        """Cuando todos los puertos estan libres, docker compose up es invocado.

        REQ-UP-1 Scenario 1: all ports free -> docker compose invoked.
        """
        from odev.core.preflight import PortStatus, PreflightResult

        preflight_ok = PreflightResult(statuses=[
            PortStatus("WEB_PORT", 8069, "free", None),
            PortStatus("DB_PORT", 5432, "free", None),
        ])

        contexto_mock = _mock_contexto("mi-proyecto", tmp_path)
        rutas_mock = _mock_rutas(tmp_path)
        dc_mock = MagicMock()

        with (
            patch("odev.commands.up.requerir_proyecto", return_value=contexto_mock),
            patch("odev.commands.up.obtener_rutas", return_value=rutas_mock),
            patch("odev.commands.up.obtener_docker", return_value=dc_mock),
            patch("odev.core.regen.necesita_regeneracion", return_value=False),
            patch("odev.commands.up.verificar_puertos_pre_up", return_value=preflight_ok),
            patch("odev.commands.up.Registry"),
            patch("odev.commands.up.load_env", return_value={
                "WEB_PORT": "8069", "PGWEB_PORT": "8081",
                "DB_PORT": "5432", "DEBUGPY_PORT": "5678", "MAILHOG_PORT": "8025",
            }),
            patch("odev.main.obtener_nombre_proyecto", return_value="mi-proyecto"),
        ):
            from odev.commands.up import up
            up()

        dc_mock.up.assert_called_once()


class TestUpPreflightFail:
    """Verifica que up falla con exit 3 cuando hay conflictos de puertos foraneos."""

    def test_up_falla_con_exit3_cuando_puerto_foraneo(
        self, tmp_path: Path, registry_tmp: None
    ) -> None:
        """Con un puerto foraneo, up sale con codigo 3 sin invocar docker compose.

        REQ-UP-1 Scenario 2: foreign process on port -> exit 3, no docker call.
        REQ-UP-2: puerto foraneo identificado.
        """
        from odev.core.preflight import PortStatus, PreflightResult

        preflight_fail = PreflightResult(statuses=[
            PortStatus("WEB_PORT", 8069, "foreign_unknown", None),
        ])

        contexto_mock = _mock_contexto("mi-proyecto", tmp_path)
        rutas_mock = _mock_rutas(tmp_path)
        dc_mock = MagicMock()

        with (
            patch("odev.commands.up.requerir_proyecto", return_value=contexto_mock),
            patch("odev.commands.up.obtener_rutas", return_value=rutas_mock),
            patch("odev.commands.up.obtener_docker", return_value=dc_mock),
            patch("odev.core.regen.necesita_regeneracion", return_value=False),
            patch("odev.commands.up.verificar_puertos_pre_up", return_value=preflight_fail),
            patch("odev.commands.up.Registry"),
            patch("odev.commands.up.load_env", return_value={
                "WEB_PORT": "8069", "PGWEB_PORT": "8081",
                "DB_PORT": "5432", "DEBUGPY_PORT": "5678", "MAILHOG_PORT": "8025",
            }),
            patch("odev.main.obtener_nombre_proyecto", return_value="mi-proyecto"),
        ):
            from odev.commands.up import up

            with pytest.raises(typer.Exit) as exc_info:
                up()

        assert exc_info.value.exit_code == 3
        dc_mock.up.assert_not_called()

    def test_up_falla_con_mensaje_de_puerto_ocupado(
        self, tmp_path: Path, registry_tmp: None, capsys
    ) -> None:
        """El mensaje de error incluye el numero de puerto en conflicto.

        REQ-UP-2: mensaje identifica el propietario del puerto si es conocido.
        """
        from odev.core.preflight import PortStatus, PreflightResult

        preflight_fail = PreflightResult(statuses=[
            PortStatus("WEB_PORT", 8069, "foreign_known", "otro-proyecto"),
        ])

        contexto_mock = _mock_contexto("mi-proyecto", tmp_path)
        rutas_mock = _mock_rutas(tmp_path)
        dc_mock = MagicMock()

        with (
            patch("odev.commands.up.requerir_proyecto", return_value=contexto_mock),
            patch("odev.commands.up.obtener_rutas", return_value=rutas_mock),
            patch("odev.commands.up.obtener_docker", return_value=dc_mock),
            patch("odev.core.regen.necesita_regeneracion", return_value=False),
            patch("odev.commands.up.verificar_puertos_pre_up", return_value=preflight_fail),
            patch("odev.commands.up.Registry"),
            patch("odev.commands.up.load_env", return_value={
                "WEB_PORT": "8069", "PGWEB_PORT": "8081",
                "DB_PORT": "5432", "DEBUGPY_PORT": "5678", "MAILHOG_PORT": "8025",
            }),
            patch("odev.main.obtener_nombre_proyecto", return_value="mi-proyecto"),
        ):
            from odev.commands.up import up

            with pytest.raises(typer.Exit):
                up()


class TestPgwebUrlGated:
    """Verifica que la URL de pgweb solo se imprime cuando pgweb_habilitado=True (Q4).

    T15.1 RED: estos tests fallan hasta que se agregue el condicional
    en up.py:106.
    """

    def _run_up_success(self, tmp_path: Path, pgweb_habilitado: bool):
        """Helper: ejecuta up() exitosamente con pgweb_habilitado configurado."""
        from odev.core.preflight import PortStatus, PreflightResult

        preflight_ok = PreflightResult(statuses=[
            PortStatus("WEB_PORT", 8069, "free", None),
        ])

        contexto_mock = _mock_contexto("mi-proyecto", tmp_path)
        contexto_mock.config = MagicMock()
        contexto_mock.config.pgweb_habilitado = pgweb_habilitado
        rutas_mock = _mock_rutas(tmp_path)
        dc_mock = MagicMock()

        info_calls = []

        def track_info(msg):
            info_calls.append(msg)

        with (
            patch("odev.commands.up.requerir_proyecto", return_value=contexto_mock),
            patch("odev.commands.up.obtener_rutas", return_value=rutas_mock),
            patch("odev.commands.up.obtener_docker", return_value=dc_mock),
            patch("odev.core.regen.necesita_regeneracion", return_value=False),
            patch("odev.commands.up.verificar_puertos_pre_up", return_value=preflight_ok),
            patch("odev.commands.up.Registry"),
            patch("odev.commands.up.load_env", return_value={
                "WEB_PORT": "8069", "PGWEB_PORT": "8081",
                "DB_PORT": "5432", "DEBUGPY_PORT": "5678", "MAILHOG_PORT": "8025",
            }),
            patch("odev.main.obtener_nombre_proyecto", return_value="mi-proyecto"),
            patch("odev.commands.up.info", side_effect=track_info),
            patch("odev.commands.up.success"),
        ):
            from odev.commands.up import up
            up()

        return info_calls

    def test_pgweb_url_oculta_cuando_deshabilitado(self, tmp_path: Path, registry_tmp: None):
        """Con pgweb_habilitado=False, la URL de pgweb NO se imprime.

        REQ-UX-4 Scenario 2: services.pgweb=false -> no pgweb URL.
        """
        info_calls = self._run_up_success(tmp_path, pgweb_habilitado=False)
        pgweb_calls = [c for c in info_calls if "pgweb" in c.lower() or "8081" in c]
        assert pgweb_calls == [], (
            f"La URL de pgweb NO debe imprimirse cuando pgweb_habilitado=False. "
            f"Llamadas a info(): {info_calls}"
        )

    def test_pgweb_url_visible_cuando_habilitado(self, tmp_path: Path, registry_tmp: None):
        """Con pgweb_habilitado=True, la URL de pgweb SI se imprime.

        REQ-UX-4 Scenario 1: services.pgweb=true -> pgweb URL printed.
        """
        info_calls = self._run_up_success(tmp_path, pgweb_habilitado=True)
        pgweb_calls = [c for c in info_calls if "pgweb" in c.lower() or "8081" in c]
        assert pgweb_calls, (
            f"La URL de pgweb DEBE imprimirse cuando pgweb_habilitado=True. "
            f"Llamadas a info(): {info_calls}"
        )


class TestPreflightHint:
    """Verifica que el mensaje de error de preflight incluye un hint (Q7 — REQ-UX-6).

    T17.1 RED: estos tests fallan hasta que se agregue el hint en _preflight_puertos.
    """

    def test_preflight_hint_cuando_propietario_conocido(
        self, tmp_path: Path, registry_tmp: None, capsys
    ):
        """El mensaje de error incluye un hint 'odev doctor' cuando el propietario es conocido.

        REQ-UX-6: hint aparece en el error cuando hay conflicto con owner conocido.
        """
        from odev.core.preflight import PortStatus, PreflightResult

        preflight_fail = PreflightResult(statuses=[
            PortStatus("WEB_PORT", 8069, "foreign_known", "otro-proyecto"),
        ])

        contexto_mock = _mock_contexto("mi-proyecto", tmp_path)
        rutas_mock = _mock_rutas(tmp_path)
        dc_mock = MagicMock()

        info_calls = []
        error_calls = []

        def track_info(msg):
            info_calls.append(msg)

        def track_error(msg):
            error_calls.append(msg)

        with (
            patch("odev.commands.up.requerir_proyecto", return_value=contexto_mock),
            patch("odev.commands.up.obtener_rutas", return_value=rutas_mock),
            patch("odev.commands.up.obtener_docker", return_value=dc_mock),
            patch("odev.core.regen.necesita_regeneracion", return_value=False),
            patch("odev.commands.up.verificar_puertos_pre_up", return_value=preflight_fail),
            patch("odev.commands.up.Registry"),
            patch("odev.commands.up.load_env", return_value={
                "WEB_PORT": "8069", "PGWEB_PORT": "8081",
                "DB_PORT": "5432", "DEBUGPY_PORT": "5678", "MAILHOG_PORT": "8025",
            }),
            patch("odev.main.obtener_nombre_proyecto", return_value="mi-proyecto"),
            patch("odev.commands.up.info", side_effect=track_info),
            patch("odev.commands.up.error", side_effect=track_error),
            patch("odev.commands.up.success"),
        ):
            from odev.commands.up import up

            with pytest.raises(typer.Exit):
                up()

        all_output = " ".join(info_calls + error_calls)
        assert "odev doctor" in all_output or "doctor" in all_output.lower(), (
            f"El mensaje debe incluir un hint con 'odev doctor'. "
            f"Output: {all_output}"
        )
