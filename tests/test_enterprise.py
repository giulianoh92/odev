"""Tests para odev.commands.enterprise — subcomandos enterprise status y link."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from odev.commands.enterprise import (
    ENTERPRISE_DIR,
    _contar_modulos,
    _tamano_directorio,
    _version_dir,
    enterprise_link,
    enterprise_status,
)


class TestVersionDir:
    """Tests para la funcion _version_dir."""

    def test_retorna_ruta_correcta(self) -> None:
        """_version_dir retorna ENTERPRISE_DIR / version."""
        resultado = _version_dir("19.0")
        assert resultado == ENTERPRISE_DIR / "19.0"

    def test_retorna_path_instance(self) -> None:
        """_version_dir retorna un objeto Path."""
        resultado = _version_dir("18.0")
        assert isinstance(resultado, Path)


class TestContarModulos:
    """Tests para la funcion _contar_modulos."""

    def test_cuenta_modulos_correctamente(self, tmp_path: Path) -> None:
        """Cuenta subdirectorios que tienen __manifest__.py."""
        # Crear 3 modulos
        for nombre in ["modulo_a", "modulo_b", "modulo_c"]:
            mod_dir = tmp_path / nombre
            mod_dir.mkdir()
            (mod_dir / "__manifest__.py").write_text("{}")

        # Crear directorio sin manifest (no deberia contar)
        (tmp_path / "no_es_modulo").mkdir()

        assert _contar_modulos(tmp_path) == 3

    def test_retorna_cero_si_no_existe(self, tmp_path: Path) -> None:
        """Retorna 0 si el directorio no existe."""
        assert _contar_modulos(tmp_path / "inexistente") == 0

    def test_retorna_cero_para_directorio_vacio(self, tmp_path: Path) -> None:
        """Retorna 0 para un directorio vacio."""
        assert _contar_modulos(tmp_path) == 0


class TestTamanoDirectorio:
    """Tests para la funcion _tamano_directorio."""

    def test_retorna_cero_si_no_existe(self, tmp_path: Path) -> None:
        """Retorna 0.0 si el directorio no existe."""
        assert _tamano_directorio(tmp_path / "inexistente") == 0.0

    def test_calcula_tamano(self, tmp_path: Path) -> None:
        """Calcula tamano total de archivos en el directorio."""
        (tmp_path / "archivo.txt").write_text("x" * 1024)
        tamano = _tamano_directorio(tmp_path)
        assert tamano > 0


class TestEnterpriseStatusEmpty:
    """Tests para enterprise_status cuando no hay versiones instaladas."""

    def test_status_empty(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """Muestra mensaje informativo cuando no hay versiones enterprise."""
        with patch("odev.commands.enterprise.ENTERPRISE_DIR", tmp_path / "enterprise"):
            enterprise_status()
        # No deberia lanzar excepciones — el mensaje se imprime via Rich console


class TestEnterpriseStatusWithVersions:
    """Tests para enterprise_status con versiones disponibles."""

    def test_status_with_versions(self, tmp_path: Path) -> None:
        """Lista versiones enterprise instaladas."""
        enterprise_dir = tmp_path / "enterprise"
        enterprise_dir.mkdir()

        # Crear version 19.0 con 2 modulos
        v19 = enterprise_dir / "19.0"
        v19.mkdir()
        for nombre in ["account_accountant", "web_enterprise"]:
            mod = v19 / nombre
            mod.mkdir()
            (mod / "__manifest__.py").write_text("{}")

        with (
            patch("odev.commands.enterprise.ENTERPRISE_DIR", enterprise_dir),
            patch("odev.commands.enterprise.Registry") as mock_registry,
        ):
            mock_registry.return_value.listar.return_value = []
            enterprise_status()
        # Should not raise


class TestEnterpriseLinkUpdatesYaml:
    """Tests para enterprise_link actualizando odev.yaml."""

    def test_link_updates_yaml(self, tmp_path: Path) -> None:
        """enterprise_link actualiza odev.yaml con enterprise.enabled y path."""
        # Preparar directorio enterprise compartido
        enterprise_dir = tmp_path / "shared_enterprise"
        enterprise_dir.mkdir()
        v19 = enterprise_dir / "19.0"
        v19.mkdir()
        mod = v19 / "web_enterprise"
        mod.mkdir()
        (mod / "__manifest__.py").write_text("{}")

        # Preparar proyecto con odev.yaml
        project_dir = tmp_path / "proyecto"
        project_dir.mkdir()
        config_yaml = {
            "odev_min_version": "0.1.0",
            "odoo": {"version": "19.0", "image": "odoo:19"},
            "database": {"image": "pgvector/pgvector:pg16"},
            "enterprise": {"enabled": False, "path": "./enterprise"},
            "services": {"pgweb": True},
            "paths": {
                "addons": ["./addons"],
                "config": "./config",
                "snapshots": "./snapshots",
                "logs": "./logs",
                "docs": "./docs",
            },
            "project": {"name": "test-link", "description": "Test"},
        }
        ruta_yaml = project_dir / ".odev.yaml"
        ruta_yaml.write_text(
            yaml.dump(config_yaml, default_flow_style=False, allow_unicode=True)
        )

        # Crear directorios necesarios para regeneracion
        (project_dir / "config").mkdir()
        (project_dir / "addons").mkdir()
        (project_dir / "docker-compose.yml").write_text("version: '3'\nservices:\n  web:\n    image: odoo:19\n")
        (project_dir / ".env").write_text("PROJECT_NAME=test-link\nODOO_VERSION=19.0\n")

        # Mock del contexto del proyecto
        from odev.core.project import ProjectConfig
        from odev.core.resolver import ModoProyecto, ProjectContext

        config = ProjectConfig(project_dir)
        contexto = ProjectContext(
            nombre="test-link",
            modo=ModoProyecto.INLINE,
            directorio_config=project_dir,
            directorio_trabajo=project_dir,
            config=config,
        )

        with (
            patch("odev.commands.enterprise.ENTERPRISE_DIR", enterprise_dir),
            patch("odev.commands.enterprise.requerir_proyecto", return_value=contexto),
            patch("odev.commands.enterprise.regenerar_configuracion") as mock_regen,
            patch("odev.main._nombre_proyecto", None),
        ):
            from odev.core.regen import RegenResult
            mock_regen.return_value = RegenResult()

            enterprise_link(version="19.0")

        # Verificar que odev.yaml fue actualizado
        datos_actualizados = yaml.safe_load(ruta_yaml.read_text())
        assert datos_actualizados["enterprise"]["enabled"] is True
        assert datos_actualizados["enterprise"]["path"] == str(v19.resolve())

    def test_link_error_no_enterprise(self, tmp_path: Path) -> None:
        """enterprise_link lanza error si no existe enterprise para la version."""
        enterprise_dir = tmp_path / "empty_enterprise"
        enterprise_dir.mkdir()

        project_dir = tmp_path / "proyecto"
        project_dir.mkdir()
        config_yaml = {
            "odev_min_version": "0.1.0",
            "odoo": {"version": "19.0", "image": "odoo:19"},
            "enterprise": {"enabled": False, "path": "./enterprise"},
            "paths": {"addons": ["./addons"]},
            "project": {"name": "test-link"},
        }
        ruta_yaml = project_dir / ".odev.yaml"
        ruta_yaml.write_text(
            yaml.dump(config_yaml, default_flow_style=False, allow_unicode=True)
        )

        from odev.core.project import ProjectConfig
        from odev.core.resolver import ModoProyecto, ProjectContext

        config = ProjectConfig(project_dir)
        contexto = ProjectContext(
            nombre="test-link",
            modo=ModoProyecto.INLINE,
            directorio_config=project_dir,
            directorio_trabajo=project_dir,
            config=config,
        )

        with (
            patch("odev.commands.enterprise.ENTERPRISE_DIR", enterprise_dir),
            patch("odev.commands.enterprise.requerir_proyecto", return_value=contexto),
            patch("odev.main._nombre_proyecto", None),
            pytest.raises(SystemExit),
        ):
            enterprise_link(version="19.0")


class TestAdoptSharedEnterprise:
    """Tests para la deteccion de enterprise compartido en adopt."""

    def test_construir_valores_detecta_shared_enterprise(self, tmp_path: Path) -> None:
        """_construir_valores detecta y usa enterprise compartido cuando no hay local."""
        from odev.commands.adopt import _construir_valores
        from odev.core.detect import RepoLayout, TipoRepo

        # Preparar enterprise compartido
        enterprise_dir = tmp_path / "shared_enterprise"
        enterprise_dir.mkdir()
        v19 = enterprise_dir / "19.0"
        v19.mkdir()
        mod = v19 / "web_enterprise"
        mod.mkdir()
        (mod / "__manifest__.py").write_text("{}")

        # Layout sin enterprise local
        layout = RepoLayout(
            tipo=TipoRepo.MULTI_ADDON,
            rutas_addons=[tmp_path / "addons"],
            tiene_enterprise=False,
            tiene_submodulos=False,
            ruta_raiz=tmp_path,
            modulos_encontrados=5,
        )

        directorio_config = tmp_path / "config"
        directorio_config.mkdir()

        extras = {
            "web_port": "8069",
            "pgweb_port": "8081",
            "db_name": "odoo_db",
            "db_user": "odoo",
            "db_password": "odoo",
            "idioma": "en_US",
            "sin_demo": "all",
            "habilitar_debugpy": False,
            "habilitar_pgweb": True,
        }

        with patch("odev.commands.enterprise.ENTERPRISE_DIR", enterprise_dir):
            valores = _construir_valores(
                nombre="test-adopt",
                ruta=tmp_path,
                layout=layout,
                odoo_version="19.0",
                directorio_config=directorio_config,
                puertos={"DB_PORT": 5432, "DEBUGPY_PORT": 5678, "MAILHOG_PORT": 8025},
                extras=extras,
                no_interactive=True,
            )

        assert valores["enterprise_enabled"] is True
        assert valores["enterprise_path"] == str(v19.resolve())

    def test_construir_valores_sin_shared_enterprise(self, tmp_path: Path) -> None:
        """_construir_valores usa './enterprise' cuando no hay enterprise compartido ni local."""
        from odev.commands.adopt import _construir_valores
        from odev.core.detect import RepoLayout, TipoRepo

        # Enterprise dir vacio
        enterprise_dir = tmp_path / "shared_enterprise"
        enterprise_dir.mkdir()

        layout = RepoLayout(
            tipo=TipoRepo.MULTI_ADDON,
            rutas_addons=[tmp_path / "addons"],
            tiene_enterprise=False,
            tiene_submodulos=False,
            ruta_raiz=tmp_path,
            modulos_encontrados=5,
        )

        directorio_config = tmp_path / "config"
        directorio_config.mkdir()

        extras = {
            "web_port": "8069",
            "pgweb_port": "8081",
            "db_name": "odoo_db",
            "db_user": "odoo",
            "db_password": "odoo",
            "idioma": "en_US",
            "sin_demo": "all",
            "habilitar_debugpy": False,
            "habilitar_pgweb": True,
        }

        with patch("odev.commands.enterprise.ENTERPRISE_DIR", enterprise_dir):
            valores = _construir_valores(
                nombre="test-adopt",
                ruta=tmp_path,
                layout=layout,
                odoo_version="19.0",
                directorio_config=directorio_config,
                puertos={"DB_PORT": 5432, "DEBUGPY_PORT": 5678, "MAILHOG_PORT": 8025},
                extras=extras,
                no_interactive=True,
            )

        assert valores["enterprise_enabled"] is False
        assert valores["enterprise_path"] == "./enterprise"
