"""Fixtures compartidos para los tests del CLI odev.

Provee directorios temporales, archivos .env mock, .odev.yaml mock,
docker-compose.yml mock y otras utilidades reutilizables.
"""

import textwrap
from pathlib import Path

import pytest
import yaml


@pytest.fixture
def directorio_proyecto(tmp_path: Path) -> Path:
    """Crea un directorio temporal con estructura basica de proyecto odev.

    Incluye .odev.yaml, .env, docker-compose.yml y directorios estandar.

    Returns:
        Path al directorio raiz del proyecto temporal.
    """
    # Crear .odev.yaml
    config_yaml = {
        "odev_min_version": "0.1.0",
        "odoo": {
            "version": "19.0",
            "image": "odoo:19",
        },
        "database": {
            "image": "pgvector/pgvector:pg16",
        },
        "enterprise": {
            "enabled": False,
            "path": "./enterprise",
        },
        "services": {
            "pgweb": True,
        },
        "paths": {
            "addons": "./addons",
            "config": "./config",
            "snapshots": "./snapshots",
            "logs": "./logs",
            "docs": "./docs",
        },
        "project": {
            "name": "mi-proyecto-test",
            "description": "Proyecto de prueba",
        },
        "sdd": {
            "enabled": True,
            "language": "es",
        },
    }
    ruta_yaml = tmp_path / ".odev.yaml"
    ruta_yaml.write_text(
        yaml.dump(config_yaml, default_flow_style=False, allow_unicode=True),
        encoding="utf-8",
    )

    # Crear .env
    contenido_env = textwrap.dedent("""\
        PROJECT_NAME=mi-proyecto-test
        COMPOSE_PROJECT_NAME=mi-proyecto-test
        ODOO_VERSION=19.0
        WEB_PORT=8069
        DB_PORT=5432
        DB_NAME=odoo_db
        DB_USER=odoo
        DB_PASSWORD=odoo
        DB_HOST=db
        PGWEB_PORT=8081
        DEBUGPY=False
        DEBUGPY_PORT=5678
        ADMIN_PASSWORD=admin
    """)
    (tmp_path / ".env").write_text(contenido_env)

    # Crear docker-compose.yml basico
    (tmp_path / "docker-compose.yml").write_text("version: '3'\nservices:\n  web:\n    image: odoo:19\n")

    # Crear directorios estandar
    for nombre in ["addons", "enterprise", "config", "snapshots", "logs", "docs"]:
        directorio = tmp_path / nombre
        directorio.mkdir(exist_ok=True)
        (directorio / ".gitkeep").touch()

    return tmp_path


@pytest.fixture
def directorio_legacy(tmp_path: Path) -> Path:
    """Crea un directorio temporal con estructura legacy (repo del CLI viejo).

    La clave es que exista docker-compose.yml + cli/main.py.

    Returns:
        Path al directorio raiz del proyecto legacy.
    """
    (tmp_path / "docker-compose.yml").write_text("version: '3'\nservices:\n  web:\n    image: odoo:19\n")
    cli_dir = tmp_path / "cli"
    cli_dir.mkdir()
    (cli_dir / "main.py").write_text("# CLI viejo\n")
    (tmp_path / ".env").write_text("PROJECT_NAME=legacy-project\nODOO_VERSION=17.0\n")
    (tmp_path / "addons").mkdir()
    return tmp_path


@pytest.fixture
def directorio_vacio(tmp_path: Path) -> Path:
    """Crea un directorio temporal vacio (sin indicadores de proyecto).

    Returns:
        Path al directorio temporal vacio.
    """
    return tmp_path


@pytest.fixture
def archivo_env_mock(tmp_path: Path) -> Path:
    """Crea un archivo .env mock con valores de prueba.

    Returns:
        Path al archivo .env creado.
    """
    contenido = textwrap.dedent("""\
        PROJECT_NAME=test-project
        ODOO_VERSION=19.0
        WEB_PORT=8069
        DB_NAME=test_db
        DB_USER=test_user
        DB_PASSWORD=test_pass
        DB_HOST=db
        ADMIN_PASSWORD=admin123
    """)
    ruta = tmp_path / ".env"
    ruta.write_text(contenido)
    return ruta


@pytest.fixture
def archivo_odev_yaml(tmp_path: Path) -> Path:
    """Crea un archivo .odev.yaml mock con configuracion basica.

    Returns:
        Path al archivo .odev.yaml creado.
    """
    config = {
        "odev_min_version": "0.1.0",
        "odoo": {"version": "19.0", "image": "odoo:19"},
        "project": {"name": "yaml-test-project", "description": "Test"},
    }
    ruta = tmp_path / ".odev.yaml"
    ruta.write_text(
        yaml.dump(config, default_flow_style=False, allow_unicode=True),
        encoding="utf-8",
    )
    return ruta
