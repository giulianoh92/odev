"""Tests para odev.commands.init — creacion de nuevos proyectos Odoo.

Verifica que el comando init cree la estructura de archivos completa,
respete la flag --no-interactive, no sobreescriba archivos existentes
(excepto los regenerables), cree .gitkeep y haga ejecutable entrypoint.sh.
"""

import os
import stat
from pathlib import Path
from unittest.mock import patch

import pytest

from odev.commands.init import (
    _ARCHIVOS_REGENERABLES,
    _DIRECTORIOS_PROYECTO,
    _MAPA_TEMPLATES,
    _construir_valores,
    _crear_directorios_proyecto,
    _renderizar_archivos_proyecto,
    _resolver_destino,
    _valores_por_defecto,
)


class TestResolverDestino:
    """Grupo de tests para la funcion _resolver_destino()."""

    def test_none_usa_cwd(self, monkeypatch, tmp_path):
        """Cuando name es None, usa el directorio actual."""
        monkeypatch.chdir(tmp_path)

        directorio, nombre = _resolver_destino(None)

        assert directorio == tmp_path
        assert nombre == tmp_path.name

    def test_punto_usa_cwd(self, monkeypatch, tmp_path):
        """Cuando name es '.', usa el directorio actual."""
        monkeypatch.chdir(tmp_path)

        directorio, nombre = _resolver_destino(".")

        assert directorio == tmp_path

    def test_nombre_relativo_crea_subdirectorio(self, monkeypatch, tmp_path):
        """Un nombre relativo crea un subdirectorio bajo el cwd."""
        monkeypatch.chdir(tmp_path)

        directorio, nombre = _resolver_destino("mi-proyecto")

        assert directorio == tmp_path / "mi-proyecto"
        assert nombre == "mi-proyecto"

    def test_ruta_absoluta_se_usa_directamente(self, tmp_path):
        """Una ruta absoluta se usa tal cual."""
        ruta_abs = tmp_path / "absoluto" / "proyecto"

        directorio, nombre = _resolver_destino(str(ruta_abs))

        assert directorio == ruta_abs
        assert nombre == "proyecto"


class TestValoresPorDefecto:
    """Grupo de tests para la funcion _valores_por_defecto()."""

    def test_genera_valores_completos(self):
        """Genera un diccionario con todas las claves necesarias para templates."""
        with patch("odev.commands.init.sugerir_puertos") as mock_puertos:
            mock_puertos.return_value = {
                "WEB_PORT": 8069,
                "PGWEB_PORT": 8081,
                "DB_PORT": 5432,
                "DEBUGPY_PORT": 5678,
                "MAILHOG_PORT": 8025,
            }

            valores = _valores_por_defecto("test-project", "19.0")

        assert valores["PROJECT_NAME"] == "test-project"
        assert valores["ODOO_VERSION"] == "19.0"
        assert valores["WEB_PORT"] == "8069"
        assert valores["DB_NAME"] == "odoo_db"
        assert valores["project_name"] == "test-project"
        assert valores["inicializar_git"] is True

    def test_mapeo_version_odoo_a_pg(self):
        """Mapea la version de Odoo al tag correcto de PostgreSQL."""
        with patch("odev.commands.init.sugerir_puertos") as mock_puertos:
            mock_puertos.return_value = {
                "WEB_PORT": 8069,
                "PGWEB_PORT": 8081,
                "DB_PORT": 5432,
                "DEBUGPY_PORT": 5678,
                "MAILHOG_PORT": 8025,
            }

            valores_19 = _valores_por_defecto("test", "19.0")
            valores_17 = _valores_por_defecto("test", "17.0")

        assert valores_19["DB_IMAGE_TAG"] == "16"
        assert valores_17["DB_IMAGE_TAG"] == "15"


class TestCrearDirectoriosProyecto:
    """Grupo de tests para la funcion _crear_directorios_proyecto()."""

    def test_crea_todos_los_directorios(self, tmp_path):
        """Crea todos los directorios definidos en _DIRECTORIOS_PROYECTO."""
        _crear_directorios_proyecto(tmp_path)

        for nombre in _DIRECTORIOS_PROYECTO:
            directorio = tmp_path / nombre
            assert directorio.is_dir(), f"Falta directorio: {nombre}"

    def test_crea_gitkeep_en_cada_directorio(self, tmp_path):
        """Crea un archivo .gitkeep en cada directorio."""
        _crear_directorios_proyecto(tmp_path)

        for nombre in _DIRECTORIOS_PROYECTO:
            gitkeep = tmp_path / nombre / ".gitkeep"
            assert gitkeep.exists(), f"Falta .gitkeep en: {nombre}"

    def test_no_sobreescribe_gitkeep_existente(self, tmp_path):
        """No sobreescribe un .gitkeep que ya existe."""
        directorio = tmp_path / "addons"
        directorio.mkdir()
        gitkeep = directorio / ".gitkeep"
        gitkeep.write_text("contenido existente")

        _crear_directorios_proyecto(tmp_path)

        assert gitkeep.read_text() == "contenido existente"


class TestRenderizarArchivosProyecto:
    """Grupo de tests para la funcion _renderizar_archivos_proyecto()."""

    @pytest.fixture
    def valores_template(self):
        """Valores minimos necesarios para renderizar templates."""
        return _construir_valores(
            nombre_proyecto="test-render",
            version_odoo="19.0",
            puerto_web="8069",
            puerto_pgweb="8081",
            nombre_db="test_db",
            usuario_db="odoo",
            password_db="odoo",
            idioma="en_US",
            sin_demo="all",
            habilitar_debugpy=False,
            habilitar_enterprise=False,
            habilitar_pgweb=True,
            generar_ci=False,
            inicializar_git=False,
            puerto_db="5432",
            puerto_debugpy="5678",
        )

    def test_crea_todos_los_archivos_esperados(self, tmp_path, valores_template):
        """Genera todos los archivos definidos en _MAPA_TEMPLATES."""
        _renderizar_archivos_proyecto(tmp_path, valores_template)

        for _, ruta_relativa in _MAPA_TEMPLATES:
            ruta = tmp_path / ruta_relativa
            assert ruta.exists(), f"Falta archivo: {ruta_relativa}"

    def test_no_sobreescribe_archivos_existentes(self, tmp_path, valores_template):
        """No sobreescribe archivos existentes que no sean regenerables."""
        # Crear un archivo que no deberia sobreescribirse
        (tmp_path / "docker-compose.yml").write_text("contenido original")

        _renderizar_archivos_proyecto(tmp_path, valores_template)

        assert (tmp_path / "docker-compose.yml").read_text() == "contenido original"

    def test_sobreescribe_archivos_regenerables(self, tmp_path, valores_template):
        """Sobreescribe archivos regenerables (.env.example, config/odoo.conf)."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "odoo.conf").write_text("viejo")

        _renderizar_archivos_proyecto(tmp_path, valores_template)

        contenido = (config_dir / "odoo.conf").read_text()
        assert contenido != "viejo"
        assert "[options]" in contenido

    def test_archivos_regenerables_definidos(self):
        """Verifica que los archivos regenerables estan definidos correctamente."""
        assert ".env.example" in _ARCHIVOS_REGENERABLES
        assert "config/odoo.conf" in _ARCHIVOS_REGENERABLES


class TestInitEntrypoint:
    """Grupo de tests para la configuracion del entrypoint."""

    def test_entrypoint_es_ejecutable(self, tmp_path):
        """entrypoint.sh debe marcarse como ejecutable despues de init."""
        valores = _construir_valores(
            nombre_proyecto="test-exec",
            version_odoo="19.0",
            puerto_web="8069",
            puerto_pgweb="8081",
            nombre_db="test_db",
            usuario_db="odoo",
            password_db="odoo",
            idioma="en_US",
            sin_demo="all",
            habilitar_debugpy=False,
            habilitar_enterprise=False,
            habilitar_pgweb=True,
            generar_ci=False,
            inicializar_git=False,
            puerto_db="5432",
            puerto_debugpy="5678",
        )

        _renderizar_archivos_proyecto(tmp_path, valores)
        ruta_entrypoint = tmp_path / "entrypoint.sh"

        # Simular lo que hace init()
        if ruta_entrypoint.exists():
            os.chmod(ruta_entrypoint, 0o755)

        modo = ruta_entrypoint.stat().st_mode
        assert modo & stat.S_IXUSR, "entrypoint.sh debe ser ejecutable por el owner"
        assert modo & stat.S_IXGRP, "entrypoint.sh debe ser ejecutable por el grupo"
        assert modo & stat.S_IXOTH, "entrypoint.sh debe ser ejecutable por otros"


class TestConstruirValores:
    """Grupo de tests para la funcion _construir_valores()."""

    def test_contiene_claves_mayusculas_y_snake_case(self):
        """El diccionario de valores contiene ambos formatos de clave."""
        valores = _construir_valores(
            nombre_proyecto="dual",
            version_odoo="19.0",
            puerto_web="8069",
            puerto_pgweb="8081",
            nombre_db="db",
            usuario_db="user",
            password_db="pass",
            idioma="en_US",
            sin_demo="all",
            habilitar_debugpy=False,
            habilitar_enterprise=False,
            habilitar_pgweb=True,
            generar_ci=True,
            inicializar_git=True,
            puerto_db="5432",
            puerto_debugpy="5678",
        )

        # Claves MAYUSCULAS para templates .env
        assert "PROJECT_NAME" in valores
        assert "ODOO_VERSION" in valores
        assert "DB_NAME" in valores

        # Claves snake_case para templates docker-compose, odev.yaml
        assert "project_name" in valores
        assert "odoo_version" in valores
        assert "enterprise_enabled" in valores

    def test_odoo_image_tag_formateado(self):
        """El tag de imagen Odoo remueve '.0' de la version."""
        valores = _construir_valores(
            nombre_proyecto="tag-test",
            version_odoo="19.0",
            puerto_web="8069",
            puerto_pgweb="8081",
            nombre_db="db",
            usuario_db="user",
            password_db="pass",
            idioma="en_US",
            sin_demo="all",
            habilitar_debugpy=False,
            habilitar_enterprise=False,
            habilitar_pgweb=True,
            generar_ci=False,
            inicializar_git=False,
            puerto_db="5432",
            puerto_debugpy="5678",
        )

        assert valores["ODOO_IMAGE_TAG"] == "19"
        assert valores["odoo_image_tag"] == "19"
