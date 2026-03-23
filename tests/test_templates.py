"""Tests de renderizado de templates Jinja2.

Verifica que todos los templates del proyecto se renderizan
correctamente con un conjunto de valores representativos.
"""

from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader

from odev.core.paths import get_project_templates_dir


@pytest.fixture
def entorno_jinja():
    """Crea un entorno Jinja2 apuntando a los templates del proyecto."""
    return Environment(
        loader=FileSystemLoader(str(get_project_templates_dir())),
        keep_trailing_newline=True,
    )


@pytest.fixture
def valores_minimos():
    """Valores minimos necesarios para renderizar los templates."""
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
        "LOAD_LANGUAGE": "en_US",
        "WITHOUT_DEMO": "all",
        "DEBUGPY": "False",
        "DEBUGPY_PORT": "5678",
        "ADMIN_PASSWORD": "admin",
        "INIT_MODULES": "",
        "MAILHOG_PORT": "8025",
        "project_name": "test_project",
        "odoo_version": "19.0",
        "odoo_image_tag": "19",
        "db_image_tag": "16",
        "enterprise_enabled": False,
        "services_pgweb": True,
        "services_mailhog": True,
        "odev_version": "0.1.0",
        "project_description": "Proyecto de prueba",
        "addon_mounts": [{"host_path": "./addons", "container_path": "/mnt/extra-addons"}],
        "addon_container_paths": ["/mnt/extra-addons"],
        "addon_dirs_container": ["/mnt/extra-addons"],
        "addons_paths_list": ["./addons"],
        "project_mode": "inline",
        "odev_min_version": "0.1.0",
        "DB_FILTER": "",
    }


# Templates de proyecto y sus nombres de archivo
_TEMPLATES_PROYECTO = [
    "docker-compose.yml.j2",
    "entrypoint.sh.j2",
    "env.j2",
    "env.example.j2",
    "odoo.conf.j2",
    "odev.yaml.j2",
    "gitignore.j2",
    "pre-commit-config.yaml.j2",
    "pylintrc.j2",
    "claude-md.j2",
    "pyproject-project.toml.j2",
]


@pytest.mark.parametrize("nombre_template", _TEMPLATES_PROYECTO)
def test_template_renderiza_sin_errores(entorno_jinja, valores_minimos, nombre_template):
    """Verifica que cada template se renderiza sin errores con valores minimos."""
    template = entorno_jinja.get_template(nombre_template)
    resultado = template.render(**valores_minimos)
    assert len(resultado) > 0, f"Template {nombre_template} genero salida vacia"


def test_docker_compose_contiene_servicios(entorno_jinja, valores_minimos):
    """El docker-compose renderizado contiene los servicios esperados."""
    template = entorno_jinja.get_template("docker-compose.yml.j2")
    resultado = template.render(**valores_minimos)
    assert "db:" in resultado
    assert "web:" in resultado
    assert "pgweb:" in resultado
    assert "mailhog:" in resultado


def test_docker_compose_sin_pgweb(entorno_jinja, valores_minimos):
    """Sin pgweb habilitado, el servicio no aparece en el docker-compose."""
    valores_minimos["services_pgweb"] = False
    template = entorno_jinja.get_template("docker-compose.yml.j2")
    resultado = template.render(**valores_minimos)
    assert "pgweb:" not in resultado


def test_docker_compose_sin_mailhog(entorno_jinja, valores_minimos):
    """Sin mailhog habilitado, el servicio no aparece en el docker-compose."""
    valores_minimos["services_mailhog"] = False
    template = entorno_jinja.get_template("docker-compose.yml.j2")
    resultado = template.render(**valores_minimos)
    assert "mailhog:" not in resultado


def test_docker_compose_con_enterprise(entorno_jinja, valores_minimos):
    """Con enterprise habilitado, se monta el directorio enterprise."""
    valores_minimos["enterprise_enabled"] = True
    template = entorno_jinja.get_template("docker-compose.yml.j2")
    resultado = template.render(**valores_minimos)
    assert "enterprise" in resultado


def test_odoo_conf_contiene_addons_path(entorno_jinja, valores_minimos):
    """El odoo.conf renderizado contiene la configuracion de addons_path."""
    template = entorno_jinja.get_template("odoo.conf.j2")
    resultado = template.render(**valores_minimos)
    assert "addons_path" in resultado


def test_env_contiene_variables_clave(entorno_jinja, valores_minimos):
    """El .env renderizado contiene las variables de entorno clave."""
    template = entorno_jinja.get_template("env.j2")
    resultado = template.render(**valores_minimos)
    assert "PROJECT_NAME" in resultado
    assert "ODOO_VERSION" in resultado
    assert "DB_NAME" in resultado
    assert "WEB_PORT" in resultado
