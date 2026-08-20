"""Tests: el healthcheck de cada servicio usa una herramienta que su imagen tiene.

`sosedoff/pgweb:0.16.2` NO trae wget. Un healthcheck basado en wget devuelve
"wget: not found" en cada sondeo, asi que pgweb queda marcado `unhealthy` de
forma permanente aunque este sirviendo HTTP 200 — un falso negativo que
contamina `odev status` y `odev doctor`. Esa imagen si trae curl.

`mailhog/mailhog:v1.0.1` (Alpine) si trae wget en /usr/bin/wget: su
healthcheck queda como esta.
"""

from __future__ import annotations

import pytest
import yaml
from jinja2 import Environment, FileSystemLoader

from odev.core.paths import get_project_templates_dir


@pytest.fixture
def compose(valores_minimos_compose):
    """docker-compose.yml renderizado y parseado."""
    entorno = Environment(
        loader=FileSystemLoader(str(get_project_templates_dir())),
        keep_trailing_newline=True,
    )
    texto = entorno.get_template("docker-compose.yml.j2").render(**valores_minimos_compose)
    return yaml.safe_load(texto)


@pytest.fixture
def valores_minimos_compose():
    """Valores minimos para renderizar el compose con pgweb y mailhog activos."""
    return {
        "PROJECT_NAME": "test_project",
        "ODOO_VERSION": "19.0",
        "ODOO_IMAGE_TAG": "19",
        "WEB_PORT": "8069",
        "PGWEB_PORT": "8081",
        "DB_NAME": "test_db",
        "DB_USER": "odoo",
        "DB_PASSWORD": "odoo",
        "DB_IMAGE_TAG": "16",
        "DB_PORT": "5432",
        "DB_HOST": "db",
        "MAILHOG_PORT": "8025",
        "DEBUGPY": "False",
        "DEBUGPY_PORT": "5678",
        "project_name": "test_project",
        "odoo_version": "19.0",
        "odoo_image_tag": "19",
        "db_image_tag": "16",
        "enterprise_enabled": False,
        "services_pgweb": True,
        "services_mailhog": True,
        "odev_version": "0.1.0",
        "addon_mounts": [{"host_path": "./addons", "container_path": "/mnt/extra-addons"}],
        "addon_container_paths": ["/mnt/extra-addons"],
        "addon_dirs_container": ["/mnt/extra-addons"],
        "addons_paths_list": ["./addons"],
        "project_mode": "inline",
        "odev_min_version": "0.1.0",
        "DB_FILTER": "",
    }


def _test_healthcheck(compose: dict, servicio: str) -> str:
    """Devuelve el comando de healthcheck del servicio como texto."""
    healthcheck = compose["services"][servicio]["healthcheck"]["test"]
    return " ".join(healthcheck) if isinstance(healthcheck, list) else str(healthcheck)


class TestHealthcheckPgweb:
    """pgweb no puede sondearse con una herramienta que su imagen no tiene."""

    def test_no_usa_wget(self, compose):
        """wget no existe en sosedoff/pgweb: usarlo garantiza unhealthy eterno."""
        assert "wget" not in _test_healthcheck(compose, "pgweb")

    def test_usa_curl(self, compose):
        """curl si existe en la imagen (/usr/bin/curl) y valida la respuesta HTTP."""
        assert "curl" in _test_healthcheck(compose, "pgweb")

    def test_sondea_el_puerto_interno(self, compose):
        """pgweb escucha en 8081 dentro del contenedor, no en PGWEB_PORT del host."""
        assert "8081" in _test_healthcheck(compose, "pgweb")

    def test_falla_si_http_falla(self, compose):
        """El sondeo debe fallar ante un status HTTP de error, no solo si no conecta."""
        assert "-f" in _test_healthcheck(compose, "pgweb")


class TestHealthcheckMailhog:
    """La imagen de MailHog si trae wget: su healthcheck no cambia."""

    def test_mailhog_conserva_wget(self, compose):
        """Regresion: mailhog/mailhog trae /usr/bin/wget y reporta healthy."""
        assert "wget" in _test_healthcheck(compose, "mailhog")

    def test_mailhog_sondea_puerto_interno(self, compose):
        """MailHog sirve su UI en 8025 dentro del contenedor."""
        assert "8025" in _test_healthcheck(compose, "mailhog")
