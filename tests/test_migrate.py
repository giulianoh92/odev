"""Tests para odev.commands.migrate — migracion de proyectos legacy.

Verifica que el comando migrate detecte correctamente el modo legacy,
cree .odev.yaml, actualice .gitignore, y maneje los casos de proyecto
ya migrado o directorio vacio.
"""

from pathlib import Path
from unittest.mock import patch

import pytest
import typer
import yaml

from odev.commands.migrate import (
    _actualizar_gitignore,
    _contar_modulos,
    _crear_odev_yaml,
    _generar_env_example,
    migrate,
)


class TestCrearOdevYaml:
    """Grupo de tests para la funcion _crear_odev_yaml()."""

    def test_crea_yaml_con_valores_del_env(self, tmp_path):
        """Crea .odev.yaml con valores extraidos del .env existente."""
        valores_env = {
            "PROJECT_NAME": "mi-legacy",
            "ODOO_VERSION": "17.0",
            "ODOO_IMAGE": "odoo:17",
            "DB_IMAGE": "postgres:15",
        }

        _crear_odev_yaml(tmp_path, valores_env, "mi-legacy")

        ruta_yaml = tmp_path / ".odev.yaml"
        assert ruta_yaml.exists()
        config = yaml.safe_load(ruta_yaml.read_text())
        assert config["odoo"]["version"] == "17.0"
        assert config["project"]["name"] == "mi-legacy"

    def test_no_sobreescribe_yaml_existente(self, tmp_path):
        """No sobreescribe un .odev.yaml que ya existe."""
        (tmp_path / ".odev.yaml").write_text("contenido_original: true\n")

        _crear_odev_yaml(tmp_path, {}, "test")

        contenido = (tmp_path / ".odev.yaml").read_text()
        assert "contenido_original" in contenido

    def test_detecta_enterprise_habilitado(self, tmp_path):
        """Detecta que enterprise esta habilitado si el directorio tiene contenido."""
        enterprise_dir = tmp_path / "enterprise"
        enterprise_dir.mkdir()
        (enterprise_dir / "modulo1").mkdir()

        _crear_odev_yaml(tmp_path, {}, "test")

        config = yaml.safe_load((tmp_path / ".odev.yaml").read_text())
        assert config["enterprise"]["enabled"] is True

    def test_enterprise_deshabilitado_si_vacio(self, tmp_path):
        """Enterprise deshabilitado si el directorio esta vacio."""
        enterprise_dir = tmp_path / "enterprise"
        enterprise_dir.mkdir()

        _crear_odev_yaml(tmp_path, {}, "test")

        config = yaml.safe_load((tmp_path / ".odev.yaml").read_text())
        assert config["enterprise"]["enabled"] is False


class TestActualizarGitignore:
    """Grupo de tests para la funcion _actualizar_gitignore()."""

    def test_remueve_exclusion_de_addons(self, tmp_path):
        """Remueve la linea 'addons/' del .gitignore."""
        (tmp_path / ".gitignore").write_text("*.pyc\naddons/\n.env\n")

        _actualizar_gitignore(tmp_path)

        contenido = (tmp_path / ".gitignore").read_text()
        assert "addons/" not in contenido
        assert "*.pyc" in contenido
        assert ".env" in contenido

    def test_remueve_variantes_de_addons(self, tmp_path):
        """Remueve todas las variantes de exclusion de addons/."""
        lineas = "addons/\naddons\n/addons/\n/addons\nother/\n"
        (tmp_path / ".gitignore").write_text(lineas)

        _actualizar_gitignore(tmp_path)

        contenido = (tmp_path / ".gitignore").read_text()
        # Ninguna variante de addons debe estar presente
        for variante in ["addons/", "addons", "/addons/", "/addons"]:
            lineas_resultado = [l.strip() for l in contenido.splitlines()]
            assert variante not in lineas_resultado, f"'{variante}' sigue en .gitignore"

    def test_agrega_entradas_faltantes(self, tmp_path):
        """Agrega entradas del nuevo formato que no existen."""
        (tmp_path / ".gitignore").write_text("*.pyc\n.env\n")

        _actualizar_gitignore(tmp_path)

        contenido = (tmp_path / ".gitignore").read_text()
        assert "config/odoo.conf" in contenido
        assert "PROJECT_CONTEXT.md" in contenido

    def test_crea_gitignore_si_no_existe(self, tmp_path):
        """Crea un .gitignore nuevo si no existe."""
        assert not (tmp_path / ".gitignore").exists()

        _actualizar_gitignore(tmp_path)

        assert (tmp_path / ".gitignore").exists()
        contenido = (tmp_path / ".gitignore").read_text()
        assert "*.pyc" in contenido

    def test_no_duplica_entradas_existentes(self, tmp_path):
        """No duplica entradas que ya existen en el .gitignore."""
        (tmp_path / ".gitignore").write_text("*.pyc\nconfig/odoo.conf\n")

        _actualizar_gitignore(tmp_path)

        contenido = (tmp_path / ".gitignore").read_text()
        assert contenido.count("config/odoo.conf") == 1


class TestContarModulos:
    """Grupo de tests para la funcion _contar_modulos()."""

    def test_cuenta_modulos_con_manifest(self, tmp_path):
        """Cuenta solo subdirectorios con __manifest__.py."""
        addons_dir = tmp_path / "addons"
        addons_dir.mkdir()

        # Modulo valido
        mod1 = addons_dir / "modulo_ventas"
        mod1.mkdir()
        (mod1 / "__manifest__.py").write_text("{}")

        # Modulo valido
        mod2 = addons_dir / "modulo_compras"
        mod2.mkdir()
        (mod2 / "__manifest__.py").write_text("{}")

        # NO es modulo (sin __manifest__.py)
        no_mod = addons_dir / "utilidades"
        no_mod.mkdir()

        assert _contar_modulos(addons_dir) == 2

    def test_retorna_cero_si_vacio(self, tmp_path):
        """Retorna 0 si el directorio addons esta vacio."""
        addons_dir = tmp_path / "addons"
        addons_dir.mkdir()

        assert _contar_modulos(addons_dir) == 0

    def test_retorna_cero_si_no_es_directorio(self, tmp_path):
        """Retorna 0 si la ruta no es un directorio."""
        assert _contar_modulos(tmp_path / "inexistente") == 0


class TestGenerarEnvExample:
    """Grupo de tests para la funcion _generar_env_example()."""

    def test_genera_env_example_con_passwords_ofuscados(self, tmp_path):
        """Genera .env.example reemplazando passwords con placeholders."""
        valores = {
            "PROJECT_NAME": "test",
            "DB_PASSWORD": "secreto123",
            "ADMIN_PASSWORD": "admin_secreto",
            "DB_USER": "odoo",
        }

        _generar_env_example(tmp_path, valores)

        contenido = (tmp_path / ".env.example").read_text()
        assert "tu_password_aqui" in contenido
        assert "tu_admin_password_aqui" in contenido
        assert "secreto123" not in contenido
        assert "DB_USER=odoo" in contenido

    def test_no_sobreescribe_existente(self, tmp_path):
        """No sobreescribe .env.example si ya existe."""
        (tmp_path / ".env.example").write_text("existente")

        _generar_env_example(tmp_path, {"KEY": "value"})

        assert (tmp_path / ".env.example").read_text() == "existente"

    def test_no_genera_sin_valores_env(self, tmp_path):
        """No genera .env.example si no hay valores env."""
        _generar_env_example(tmp_path, {})

        assert not (tmp_path / ".env.example").exists()


class TestMigrateCommand:
    """Grupo de tests para el comando migrate completo."""

    def test_noop_en_modo_project(self, tmp_path, monkeypatch):
        """No hace nada si ya es un proyecto odev (modo PROJECT)."""
        (tmp_path / ".odev.yaml").write_text("odev_min_version: 0.1.0\n")
        monkeypatch.chdir(tmp_path)

        with pytest.raises(typer.Exit) as exc_info:
            migrate()

        # Exit sin codigo de error (exit_code es 0 o None)
        assert exc_info.value.exit_code in (0, None)

    def test_error_en_modo_none(self, tmp_path, monkeypatch):
        """Lanza error si no se detecta ningun proyecto."""
        aislado = tmp_path / "aislado"
        aislado.mkdir()
        monkeypatch.chdir(aislado)

        with pytest.raises(typer.Exit) as exc_info:
            migrate()

        assert exc_info.value.exit_code == 1

    def test_migra_legacy_crea_odev_yaml(self, directorio_legacy, monkeypatch):
        """En modo LEGACY, crea .odev.yaml y otros archivos."""
        monkeypatch.chdir(directorio_legacy)

        # migrate() llama a detect_mode() que deberia encontrar LEGACY
        migrate()

        assert (directorio_legacy / ".odev.yaml").exists()
        config = yaml.safe_load((directorio_legacy / ".odev.yaml").read_text())
        assert "odoo" in config
        assert "project" in config
