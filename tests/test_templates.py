"""Tests de renderizado de templates Jinja2.

Verifica que todos los templates del proyecto se renderizan
correctamente con un conjunto de valores representativos.
"""


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


def test_docker_compose_web_corre_como_root(entorno_jinja, valores_minimos):
    """El servicio web debe arrancar con user: root (patron root-then-drop).

    La imagen oficial odoo:19 arranca como usuario odoo (uid 100) por
    default, nunca como root. Sin `user: root`, la rama del entrypoint que
    instala paquetes de sistema (ej. git para deps git+) queda muerta:
    `id -u` nunca da 0 y el pip install de requirements git+ sigue fallando.
    """
    template = entorno_jinja.get_template("docker-compose.yml.j2")
    resultado = template.render(**valores_minimos)

    inicio = resultado.index("\n  web:\n")
    fin = resultado.index("\n  pgweb:\n", inicio)
    bloque_web = resultado[inicio:fin]
    assert "user: root" in bloque_web


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


def test_entrypoint_instala_git_si_falta_para_dependencias_git_plus(
    entorno_jinja, valores_minimos
):
    """Bug: requirements con git+ fallan en silencio si la imagen no trae git.

    El entrypoint debe detectar, entre los requirements.txt encontrados, si
    alguno tiene una dependencia git+ y, si el binario git no esta presente,
    instalarlo via apt-get (solo si corre como root; si no, advertir en vez
    de fallar).
    """
    template = entorno_jinja.get_template("entrypoint.sh.j2")
    resultado = template.render(**valores_minimos)

    assert "git+" in resultado
    assert "command -v git" in resultado
    assert '"$(id -u)" = "0"' in resultado
    assert "apt-get install -y --no-install-recommends git" in resultado


def test_entrypoint_no_falla_en_silencio_si_pip_install_falla(entorno_jinja, valores_minimos):
    """Bug: pip install de requirements.txt tenia `2>/dev/null || true`, silenciando errores."""
    template = entorno_jinja.get_template("entrypoint.sh.j2")
    resultado = template.render(**valores_minimos)

    assert 'pip install --break-system-packages --quiet -r "$req" 2>/dev/null || true' not in (
        resultado
    )
    # El fallo debe quedar visible (log/warning), no desaparecer.
    assert "fallo la instalacion de dependencias" in resultado


def test_entrypoint_renderizado_es_bash_valido(entorno_jinja, valores_minimos, tmp_path):
    """El entrypoint.sh renderizado debe ser sintacticamente valido (bash -n)."""
    import subprocess

    template = entorno_jinja.get_template("entrypoint.sh.j2")
    resultado = template.render(**valores_minimos)

    ruta_script = tmp_path / "entrypoint.sh"
    ruta_script.write_text(resultado)

    proceso = subprocess.run(
        ["bash", "-n", str(ruta_script)],
        capture_output=True,
        text=True,
    )
    assert proceso.returncode == 0, proceso.stderr


def test_entrypoint_dropea_privilegios_a_odoo_via_setpriv(entorno_jinja, valores_minimos):
    """El entrypoint debe bajar privilegios a odoo antes de ejecutar Odoo.

    Con el servicio web arrancando como root (para poder instalar paquetes
    de sistema), el proceso final de Odoo no debe quedar corriendo como
    root: se usa setpriv (presente en la imagen odoo:19; gosu no lo esta)
    para bajar a uid/gid odoo, exportando HOME para que pip/user-site
    apunten al directorio correcto en vez de heredar el HOME de root.
    """
    template = entorno_jinja.get_template("entrypoint.sh.j2")
    resultado = template.render(**valores_minimos)

    assert "setpriv --reuid=odoo --regid=odoo --init-groups" in resultado
    assert "export HOME=/var/lib/odoo" in resultado
    # Si no corre como root (override del usuario en compose), se mantiene
    # el exec directo sin setpriv.
    assert '"$(id -u)" = "0"' in resultado


def test_entrypoint_debugpy_tambien_dropea_privilegios(entorno_jinja, valores_minimos):
    """La variante debugpy tambien debe pasar por el drop de privilegios.

    CMD/ARGS son compartidos entre la variante normal y la de debugpy, asi
    que ambas rutas deben terminar en el mismo exec con setpriv.
    """
    valores_minimos["DEBUGPY"] = "True"
    template = entorno_jinja.get_template("entrypoint.sh.j2")
    resultado = template.render(**valores_minimos)

    assert "setpriv --reuid=odoo --regid=odoo --init-groups" in resultado
    assert '"$CMD" "${ARGS[@]}"' in resultado


def test_entrypoint_debugpy_renderizado_es_bash_valido(entorno_jinja, valores_minimos, tmp_path):
    """La variante debugpy tambien debe ser sintacticamente valida (bash -n)."""
    import subprocess

    valores_minimos["DEBUGPY"] = "True"
    template = entorno_jinja.get_template("entrypoint.sh.j2")
    resultado = template.render(**valores_minimos)

    ruta_script = tmp_path / "entrypoint.sh"
    ruta_script.write_text(resultado)

    proceso = subprocess.run(
        ["bash", "-n", str(ruta_script)],
        capture_output=True,
        text=True,
    )
    assert proceso.returncode == 0, proceso.stderr
