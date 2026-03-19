"""Gestion de configuracion del entorno: carga de .env y generacion de odoo.conf.

Portado del viejo cli/core/config.py, adaptado para usar las nuevas rutas
dinamicas de ProjectPaths y los templates bundled en el paquete pip.

Cambio clave: Los templates Jinja2 ahora se cargan del paquete pip
(via get_project_templates_dir), no del filesystem local.
"""

from pathlib import Path

from dotenv import dotenv_values
from jinja2 import Environment, FileSystemLoader

from odev.core.paths import get_project_templates_dir


def load_env(env_file: Path | None = None) -> dict[str, str | None]:
    """Lee el archivo .env y retorna sus valores como diccionario.

    Args:
        env_file: Ruta al archivo .env. Si es None, busca en el proyecto actual.

    Returns:
        Diccionario con las variables de entorno cargadas del .env.
        Si el archivo no existe, retorna un diccionario vacio.
    """
    if env_file is None:
        from odev.core.paths import ProjectPaths

        rutas = ProjectPaths()
        env_file = rutas.env_file
    if not env_file.exists():
        return {}
    return dict(dotenv_values(env_file))


def _get_jinja_env() -> Environment:
    """Crea y retorna el entorno Jinja2 configurado con los templates del paquete.

    Returns:
        Entorno Jinja2 apuntando al directorio de templates de proyecto.
    """
    return Environment(
        loader=FileSystemLoader(str(get_project_templates_dir())),
        keep_trailing_newline=True,
    )


def write_env(values: dict[str, str], dest: Path | None = None) -> Path:
    """Renderiza el template env.j2 con los valores dados y escribe el .env.

    Args:
        values: Diccionario de valores para renderizar el template.
        dest: Ruta destino para el archivo .env. Si es None, usa la ruta
              del proyecto actual.

    Returns:
        Ruta al archivo .env generado.
    """
    env = _get_jinja_env()
    template = env.get_template("env.j2")
    salida = template.render(**values)
    if dest is None:
        from odev.core.paths import ProjectPaths

        rutas = ProjectPaths()
        dest = rutas.env_file
    dest.write_text(salida)
    return dest


def generate_odoo_conf(
    env_values: dict[str, str | None] | None = None,
    config_dir: Path | None = None,
) -> Path:
    """Renderiza odoo.conf.j2 y escribe en config/odoo.conf.

    Args:
        env_values: Valores del .env para renderizar. Si es None, se cargan
                   automaticamente del .env del proyecto.
        config_dir: Directorio donde escribir odoo.conf. Si es None, usa
                   el directorio config/ del proyecto actual.

    Returns:
        Ruta al archivo odoo.conf generado.
    """
    if env_values is None:
        env_values = load_env()
    jinja_env = _get_jinja_env()
    template = jinja_env.get_template("odoo.conf.j2")
    salida = template.render(**{k: v for k, v in env_values.items() if v is not None})
    if config_dir is None:
        from odev.core.paths import ProjectPaths

        rutas = ProjectPaths()
        config_dir = rutas.config_dir
    config_dir.mkdir(parents=True, exist_ok=True)
    destino = config_dir / "odoo.conf"
    destino.write_text(salida)
    return destino
