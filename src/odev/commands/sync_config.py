"""Comando `odev sync-config` — regenera archivos de configuracion.

Util cuando editas manualmente odev.yaml y necesitas que los cambios
se reflejen en docker-compose.yml, odoo.conf, y entrypoint.sh sin
reiniciar los contenedores.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import typer
from jinja2 import Environment, FileSystemLoader

from odev import __version__
from odev.commands._helpers import obtener_rutas, requerir_proyecto
from odev.core.config import construir_addon_mounts, load_env
from odev.core.console import info, success
from odev.core.paths import get_project_templates_dir


def sync_config() -> None:
    """Regenera archivos de configuracion desde odev.yaml.

    Util cuando cambias:
    - enterprise.enabled / enterprise.path
    - paths.addons
    - odoo.version o database.image

    No reinicia contenedores; ejecuta `odev restart` manualmente
    para aplicar cambios.
    """
    from odev.main import obtener_nombre_proyecto

    contexto = requerir_proyecto(obtener_nombre_proyecto())
    rutas = obtener_rutas(contexto)
    config = contexto.config

    info("Regenerando archivos de configuracion...")

    # 1. Remove stale files to force regeneration
    files_to_remove = [
        rutas.docker_compose_file,
        rutas.config_dir / "odoo.conf",
        rutas.entrypoint_script,
    ]

    for file in files_to_remove:
        if file.exists():
            file.unlink()
            info(f"  Removido: {file.name}")

    # 2. Load .env values to build template context
    if not rutas.env_file.exists():
        from odev.core.console import error
        error("No se encontro .env - ejecuta 'odev init' primero.")
        raise typer.Exit(1)

    valores_env = load_env(rutas.env_file)

    # 3. Build template context from .env values
    valores = _construir_contexto_templates(rutas, config, valores_env)

    # 4. Regenerate docker-compose.yml, odoo.conf, entrypoint.sh
    info("  Generando docker-compose.yml...")
    _renderizar_archivo(
        rutas.docker_compose_file,
        "docker-compose.yml.j2",
        valores,
    )

    info("  Generando config/odoo.conf...")
    _renderizar_archivo(
        rutas.config_dir / "odoo.conf",
        "odoo.conf.j2",
        valores,
    )

    info("  Generando entrypoint.sh...")
    _renderizar_archivo(
        rutas.entrypoint_script,
        "entrypoint.sh.j2",
        valores,
    )

    success("Archivos de configuracion sincronizados.")
    info("Reinicia Odoo para aplicar cambios: odev restart")


def _construir_contexto_templates(
    rutas,
    config,
    valores_env: dict[str, str],
) -> dict[str, Any]:
    """Construye el diccionario de valores para renderizar templates.

    Extrae valores del .env y de odev.yaml para pasarlos a Jinja2.

    Args:
        rutas: ProjectPaths del proyecto.
        config: Configuración del proyecto (desde odev.yaml).
        valores_env: Diccionario del .env (DB_NAME, WEB_PORT, etc.).

    Returns:
        Diccionario con todos los valores necesarios para renderizar.
    """

    # Build addon mounts
    addon_mounts = []
    addon_container_paths = []
    if config and config.rutas_addons:
        addon_mounts = construir_addon_mounts(
            config.rutas_addons,
            rutas.config_dir,
        )
        addon_container_paths = [m["container_path"] for m in addon_mounts]

    enterprise_enabled = bool(config and config.enterprise_habilitado)

    return {
        # --- Variables MAYUSCULAS (para env.j2, env.example.j2, odoo.conf.j2) ---
        "PROJECT_NAME": valores_env.get("PROJECT_NAME", "odoo"),
        "ODOO_VERSION": valores_env.get("ODOO_VERSION", "19.0"),
        "ODOO_IMAGE_TAG": valores_env.get("ODOO_IMAGE_TAG", "19"),
        "WEB_PORT": valores_env.get("WEB_PORT", "8069"),
        "PGWEB_PORT": valores_env.get("PGWEB_PORT", "8081"),
        "DB_NAME": valores_env.get("DB_NAME", "odoo"),
        "DB_USER": valores_env.get("DB_USER", "odoo"),
        "DB_PASSWORD": valores_env.get("DB_PASSWORD", "odoo"),
        "DB_IMAGE_TAG": valores_env.get("DB_IMAGE_TAG", "16"),
        "DB_PORT": valores_env.get("DB_PORT", "5432"),
        "DB_HOST": "db",
        "LOAD_LANGUAGE": valores_env.get("LOAD_LANGUAGE", "es_AR"),
        "WITHOUT_DEMO": valores_env.get("WITHOUT_DEMO", "False"),
        "DEBUGPY": valores_env.get("DEBUGPY", "False"),
        "DEBUGPY_PORT": valores_env.get("DEBUGPY_PORT", "5678"),
        "ADMIN_PASSWORD": valores_env.get("ADMIN_PASSWORD", "admin"),
        "INIT_MODULES": valores_env.get("INIT_MODULES", ""),
        "MAILHOG_PORT": valores_env.get("MAILHOG_PORT", "8025"),
        # --- Variables snake_case (para docker-compose.yml.j2, entrypoint.sh.j2, etc.) ---
        "project_name": valores_env.get("PROJECT_NAME", "odoo"),
        "odoo_version": valores_env.get("ODOO_VERSION", "19.0"),
        "odoo_image_tag": valores_env.get("ODOO_IMAGE_TAG", "19"),
        "db_image_tag": valores_env.get("DB_IMAGE_TAG", "16"),
        "enterprise_enabled": enterprise_enabled,
        "services_pgweb": True,
        "services_mailhog": True,
        "odev_version": __version__,
        "project_description": "",
        "addon_mounts": addon_mounts,
        "addon_container_paths": addon_container_paths,
        "addon_dirs_container": addon_container_paths,
        "addons_paths_list": config.rutas_addons if config else ["./addons"],
        "project_mode": "inline",
        "odev_min_version": __version__,
    }


def _renderizar_archivo(
    ruta_destino: Path,
    nombre_template: str,
    valores: dict[str, Any],
) -> None:
    """Renderiza un template Jinja2 y lo escribe en ruta_destino.

    Args:
        ruta_destino: Ruta donde escribir el archivo renderizado.
        nombre_template: Nombre del template en templates/.
        valores: Diccionario de valores para renderizar.
    """
    entorno_jinja = Environment(
        loader=FileSystemLoader(str(get_project_templates_dir())),
        keep_trailing_newline=True,
    )

    # Asegurar que el directorio padre exista
    ruta_destino.parent.mkdir(parents=True, exist_ok=True)

    # Renderizar template
    template = entorno_jinja.get_template(nombre_template)
    contenido = template.render(**valores)
    ruta_destino.write_text(contenido, encoding="utf-8")
