"""Tests para odev.core.config — gestion de configuracion del entorno.

Verifica la carga de .env, escritura de .env desde templates Jinja2,
y la generacion de odoo.conf.
"""

import pytest

from odev.core.config import generate_odoo_conf, load_env, write_env


class TestLoadEnv:
    """Grupo de tests para la funcion load_env()."""

    def test_carga_env_correctamente(self, tmp_path):
        """Lee un archivo .env y retorna los valores como diccionario."""
        contenido = "DB_NAME=mi_db\nDB_USER=odoo\nDB_PASSWORD=secret\n"
        ruta_env = tmp_path / ".env"
        ruta_env.write_text(contenido)

        resultado = load_env(ruta_env)

        assert resultado["DB_NAME"] == "mi_db"
        assert resultado["DB_USER"] == "odoo"
        assert resultado["DB_PASSWORD"] == "secret"

    def test_retorna_dict_vacio_si_no_existe(self, tmp_path):
        """Retorna diccionario vacio si el archivo .env no existe."""
        ruta_env = tmp_path / ".env"

        resultado = load_env(ruta_env)

        assert resultado == {}

    def test_ignora_lineas_vacias_y_comentarios(self, tmp_path):
        """Ignora comentarios y lineas vacias en el .env."""
        contenido = "# Comentario\nKEY1=valor1\n\n# Otro comentario\nKEY2=valor2\n"
        ruta_env = tmp_path / ".env"
        ruta_env.write_text(contenido)

        resultado = load_env(ruta_env)

        assert resultado["KEY1"] == "valor1"
        assert resultado["KEY2"] == "valor2"
        assert len(resultado) == 2

    def test_maneja_valores_con_signo_igual(self, tmp_path):
        """Maneja valores que contienen el signo = correctamente."""
        contenido = "FILTER=^odoo_db$\nPASS=abc=123\n"
        ruta_env = tmp_path / ".env"
        ruta_env.write_text(contenido)

        resultado = load_env(ruta_env)

        assert resultado["FILTER"] == "^odoo_db$"
        assert resultado["PASS"] == "abc=123"


class TestWriteEnv:
    """Grupo de tests para la funcion write_env()."""

    def test_renderiza_template_y_escribe(self, tmp_path):
        """Renderiza el template env.j2 con valores y lo escribe en el destino."""
        valores = {
            "PROJECT_NAME": "test-project",
            "ODOO_VERSION": "19.0",
            "WEB_PORT": "8069",
            "DB_NAME": "test_db",
            "DB_USER": "test_user",
            "DB_PASSWORD": "test_pass",
            "DB_IMAGE_TAG": "16",
            "DB_PORT": "5432",
            "DB_HOST": "db",
            "PGWEB_PORT": "8081",
            "DEBUGPY": "False",
            "DEBUGPY_PORT": "5678",
            "ADMIN_PASSWORD": "admin",
            "LOAD_LANGUAGE": "en_US",
            "WITHOUT_DEMO": "all",
            "INIT_MODULES": "",
        }
        ruta_destino = tmp_path / ".env"

        resultado = write_env(valores, dest=ruta_destino)

        assert resultado == ruta_destino
        assert ruta_destino.exists()
        contenido = ruta_destino.read_text()
        assert "PROJECT_NAME=test-project" in contenido
        assert "DB_USER=test_user" in contenido

    def test_archivo_generado_es_legible_por_load_env(self, tmp_path):
        """El .env generado por write_env es legible por load_env."""
        valores = {
            "PROJECT_NAME": "roundtrip-test",
            "ODOO_VERSION": "19.0",
            "WEB_PORT": "8069",
            "DB_NAME": "rt_db",
            "DB_USER": "rt_user",
            "DB_PASSWORD": "rt_pass",
            "DB_IMAGE_TAG": "16",
            "DB_PORT": "5432",
            "DB_HOST": "db",
            "PGWEB_PORT": "8081",
            "DEBUGPY": "False",
            "DEBUGPY_PORT": "5678",
            "ADMIN_PASSWORD": "admin",
            "LOAD_LANGUAGE": "en_US",
            "WITHOUT_DEMO": "all",
            "INIT_MODULES": "",
        }
        ruta_env = tmp_path / ".env"
        write_env(valores, dest=ruta_env)

        resultado = load_env(ruta_env)

        assert resultado["PROJECT_NAME"] == "roundtrip-test"
        assert resultado["DB_NAME"] == "rt_db"


class TestGenerateOdooConf:
    """Grupo de tests para la funcion generate_odoo_conf()."""

    def test_genera_odoo_conf_desde_valores_env(self, tmp_path):
        """Crea config/odoo.conf a partir de valores del .env."""
        config_dir = tmp_path / "config"
        valores = {
            "DB_HOST": "db",
            "DB_USER": "odoo",
            "DB_PASSWORD": "secret",
            "DB_NAME": "mi_db",
            "ADMIN_PASSWORD": "admin",
        }

        resultado = generate_odoo_conf(env_values=valores, config_dir=config_dir)

        assert resultado == config_dir / "odoo.conf"
        assert resultado.exists()
        contenido = resultado.read_text()
        assert "db_user = odoo" in contenido
        assert "db_password = secret" in contenido
        assert "admin_passwd = admin" in contenido

    def test_crea_directorio_config_si_no_existe(self, tmp_path):
        """Crea el directorio config/ si no existe al generar odoo.conf."""
        config_dir = tmp_path / "config"
        assert not config_dir.exists()

        generate_odoo_conf(env_values={"DB_HOST": "db"}, config_dir=config_dir)

        assert config_dir.exists()
        assert (config_dir / "odoo.conf").exists()

    def test_contenido_incluye_seccion_options(self, tmp_path):
        """El archivo generado incluye la seccion [options]."""
        config_dir = tmp_path / "config"
        valores = {"DB_HOST": "db", "DB_USER": "odoo", "DB_PASSWORD": "odoo"}

        generate_odoo_conf(env_values=valores, config_dir=config_dir)

        contenido = (config_dir / "odoo.conf").read_text()
        assert "[options]" in contenido

    def test_addons_path_con_un_mount(self, tmp_path):
        """Con un solo addon mount, addons_path contiene la ruta correcta (no caracteres sueltos)."""
        config_dir = tmp_path / "config"
        addon_mounts = [{"container_path": "/mnt/extra-addons", "host_path": "./addons", "nombre": "addons"}]

        generate_odoo_conf(
            env_values={"DB_HOST": "db"},
            config_dir=config_dir,
            addon_mounts=addon_mounts,
        )

        contenido = (config_dir / "odoo.conf").read_text()
        assert "addons_path = /mnt/extra-addons" in contenido
        # Verificar que NO se iteraron caracteres (el bug original)
        assert "/,m,n,t" not in contenido

    def test_addons_path_con_multiples_mounts(self, tmp_path):
        """Con multiples addon mounts, addons_path es una lista separada por comas."""
        config_dir = tmp_path / "config"
        addon_mounts = [
            {"container_path": "/mnt/extra-addons", "host_path": "./addons", "nombre": "addons"},
            {"container_path": "/mnt/extra-addons-1", "host_path": "./other", "nombre": "other"},
        ]

        generate_odoo_conf(
            env_values={"DB_HOST": "db"},
            config_dir=config_dir,
            addon_mounts=addon_mounts,
        )

        contenido = (config_dir / "odoo.conf").read_text()
        assert "addons_path = /mnt/extra-addons,/mnt/extra-addons-1" in contenido

    def test_addons_path_con_enterprise(self, tmp_path):
        """Con enterprise habilitado, addons_path incluye /mnt/enterprise-addons."""
        config_dir = tmp_path / "config"
        addon_mounts = [{"container_path": "/mnt/extra-addons", "host_path": "./addons", "nombre": "addons"}]

        generate_odoo_conf(
            env_values={"DB_HOST": "db"},
            config_dir=config_dir,
            addon_mounts=addon_mounts,
            enterprise_enabled=True,
        )

        contenido = (config_dir / "odoo.conf").read_text()
        assert "addons_path = /mnt/extra-addons,/mnt/enterprise-addons" in contenido

    def test_addons_path_sin_mounts_default(self, tmp_path):
        """Sin addon mounts, addons_path usa el valor por defecto /mnt/extra-addons."""
        config_dir = tmp_path / "config"

        generate_odoo_conf(
            env_values={"DB_HOST": "db"},
            config_dir=config_dir,
        )

        contenido = (config_dir / "odoo.conf").read_text()
        assert "addons_path = /mnt/extra-addons" in contenido
