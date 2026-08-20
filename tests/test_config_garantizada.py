"""Tests: a live odev database always carries the local dev configuration.

The invariant: if there is a database up under odev, the only valid
configuration is report.url on the container-internal port, web.base.url on
the published host port, and MailHog as the ONLY active outgoing mail server.

Two holes broke that invariant in practice:

1. `odev up` queried the config before Odoo had created the database (Odoo
   initialises it seconds after `compose up` returns), got a psql failure, and
   returned "omitido" SILENTLY. Nothing ever applied it afterwards, so the
   project ran with no report.url — PDFs printed unstyled — and no MailHog.

2. `addon-install`/`update` change the database and restart web without
   re-checking the invariant.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from odev.core.neutralize import (
    URL_REPORTES_INTERNA,
    asegurar_entorno_desarrollo,
    esperar_base_lista,
)

_LOG_OK = b"2026-07-03 10:00:01,100 1 INFO db odoo.modules.loading: Modules loaded.\n"
_CAPTURE_OK = (b"", _LOG_OK, 0)


def _estado_ok(puerto: str = "8070") -> bytes:
    """Estado psql que ya cumple el invariante."""
    return f"{URL_REPORTES_INTERNA}|http://localhost:{puerto}|0|1\n".encode()


@pytest.fixture
def dc_mock():
    """DockerCompose mockeado."""
    mock = MagicMock()
    mock.exec_cmd.return_value = MagicMock(stdout=b"", returncode=0)
    return mock


class TestEsperarBaseLista:
    """esperar_base_lista() sondea sin abortar el comando."""

    def test_true_si_ya_esta_lista(self, dc_mock):
        """Una sola consulta cuando la base ya tiene esquema Odoo."""
        dc_mock.exec_capture.return_value = (b"t\n", b"", 0)

        with patch("time.sleep") as mock_sleep:
            assert esperar_base_lista(dc_mock, "odoo_db", "odoo") is True

        mock_sleep.assert_not_called()
        assert dc_mock.exec_capture.call_count == 1

    def test_true_cuando_aparece_en_reintento(self, dc_mock):
        """Reintenta mientras psql falla y devuelve True al aparecer."""
        dc_mock.exec_capture.side_effect = [
            (b"", b"FATAL: database does not exist", 2),
            (b"f\n", b"", 0),
            (b"t\n", b"", 0),
        ]

        with patch("time.sleep"):
            assert esperar_base_lista(dc_mock, "odoo_db", "odoo", intentos=5, intervalo=1) is True

    def test_false_al_agotar_intentos_sin_abortar(self, dc_mock):
        """Devuelve False, no lanza: el caller decide si avisa o sigue."""
        dc_mock.exec_capture.return_value = (b"", b"FATAL", 2)

        with patch("time.sleep"):
            resultado = esperar_base_lista(dc_mock, "odoo_db", "odoo", intentos=3, intervalo=1)

        assert resultado is False
        assert dc_mock.exec_capture.call_count == 3

    def test_valida_nombre_bd(self, dc_mock):
        """No interpola un nombre de base con metacaracteres."""
        with pytest.raises(ValueError, match="invalido"):
            esperar_base_lista(dc_mock, "odoo'; DROP TABLE--", "odoo")


class TestAsegurarConEspera:
    """asegurar_entorno_desarrollo(esperar=True) cubre la base que nace tarde."""

    def test_espera_y_aplica_cuando_la_base_aparece(self, dc_mock):
        """Con esperar=True aplica la config una vez que la base existe."""
        dc_mock.exec_capture.side_effect = [
            (b"", b"FATAL: database does not exist", 2),  # primer sondeo del estado
            (b"t\n", b"", 0),                             # base ya lista
            (b"|||\n", b"", 0),                           # estado real: nada configurado
        ]

        with patch("time.sleep"):
            resultado = asegurar_entorno_desarrollo(
                dc_mock, "odoo_db", "odoo", "8070", esperar=True, intentos=3, intervalo=1
            )

        assert resultado == "aplicado"

    def test_omitido_si_la_base_nunca_aparece(self, dc_mock):
        """Con esperar=True devuelve 'omitido' tras agotar el timeout."""
        dc_mock.exec_capture.return_value = (b"", b"FATAL", 2)

        with patch("time.sleep"):
            resultado = asegurar_entorno_desarrollo(
                dc_mock, "odoo_db", "odoo", "8070", esperar=True, intentos=2, intervalo=1
            )

        assert resultado == "omitido"

    def test_sin_espera_es_el_comportamiento_previo(self, dc_mock):
        """Por defecto no espera: un solo sondeo y 'omitido'."""
        dc_mock.exec_capture.return_value = (b"", b"FATAL", 2)

        with patch("time.sleep") as mock_sleep:
            resultado = asegurar_entorno_desarrollo(dc_mock, "odoo_db", "odoo", "8070")

        assert resultado == "omitido"
        mock_sleep.assert_not_called()
        assert dc_mock.exec_capture.call_count == 1


class TestUpNuncaOmiteEnSilencio:
    """`odev up` avisa si no pudo garantizar la configuracion."""

    def test_omitido_emite_aviso(self, capsys):
        """Un 'omitido' deja rastro en la salida, no silencio."""
        from odev.commands.up import _asegurar_parametros_desarrollo

        dc = MagicMock()
        with patch(
            "odev.core.neutralize.asegurar_entorno_desarrollo",
            return_value="omitido",
        ):
            _asegurar_parametros_desarrollo(dc, {"DB_NAME": "odoo_db", "DB_USER": "odoo"}, "8070")

        salida = capsys.readouterr().out
        assert "odoo_db" in salida or "base" in salida.lower()

    def test_up_pide_espera(self):
        """up invoca el aseguramiento con esperar=True."""
        from odev.commands.up import _asegurar_parametros_desarrollo

        dc = MagicMock()
        with patch(
            "odev.core.neutralize.asegurar_entorno_desarrollo",
            return_value="sin_cambios",
        ) as mock_asegurar:
            _asegurar_parametros_desarrollo(dc, {"DB_NAME": "odoo_db", "DB_USER": "odoo"}, "8070")

        assert mock_asegurar.call_args.kwargs.get("esperar") is True


def _make_contexto(tmp_path: Path) -> MagicMock:
    ctx = MagicMock()
    ctx.directorio_config = tmp_path
    ctx.nombre = "test-project"
    ctx.config = MagicMock()
    ctx.config.rutas_addons = None
    return ctx


class TestInstallYUpdateReaseguran:
    """addon-install y update dejan la base cumpliendo el invariante."""

    def _invocar(self, modulo_cmd: str, tmp_path: Path):
        """Invoca install o update con todo mockeado; retorna el mock de asegurar."""
        if modulo_cmd == "install":
            from odev.commands.install import install as comando
            prefijo = "odev.commands.install"
        else:
            from odev.commands.update import update as comando
            prefijo = "odev.commands.update"

        ctx = _make_contexto(tmp_path)
        dc = MagicMock()
        dc.exec_capture = MagicMock(return_value=_CAPTURE_OK)

        with (
            patch(f"{prefijo}.requerir_proyecto", return_value=ctx),
            patch(f"{prefijo}.obtener_docker", return_value=dc),
            patch(f"{prefijo}.obtener_rutas") as mock_rutas,
            patch(f"{prefijo}.load_env", return_value={"DB_NAME": "test_db", "WEB_PORT": "8070"}),
            patch("odev.main.obtener_nombre_proyecto", return_value="test-project"),
            patch("odev.commands._helpers.listar_modulos_disponibles", return_value=set()),
            patch(
                "odev.core.neutralize.asegurar_entorno_desarrollo",
                return_value="sin_cambios",
            ) as mock_asegurar,
        ):
            mock_rutas.return_value.env_file = tmp_path / ".env"
            comando(module="base", no_validate=True, verbose=False)

        return mock_asegurar

    def test_install_reasegura(self, tmp_path):
        """addon-install verifica el invariante al terminar."""
        mock_asegurar = self._invocar("install", tmp_path)
        mock_asegurar.assert_called_once()

    def test_update_reasegura(self, tmp_path):
        """update verifica el invariante al terminar."""
        mock_asegurar = self._invocar("update", tmp_path)
        mock_asegurar.assert_called_once()

    def test_reasegura_con_el_puerto_publicado(self, tmp_path):
        """El puerto que se escribe en web.base.url viene del .env."""
        mock_asegurar = self._invocar("install", tmp_path)
        args = mock_asegurar.call_args
        assert "8070" in args[0] or args.kwargs.get("puerto_web") == "8070"
