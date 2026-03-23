"""Comando `odev adopt` — adopta un proyecto Odoo existente.

Ejecuta un wizard interactivo (o usa valores por defecto con --no-interactive)
para detectar el layout de un directorio Odoo existente, recopilar la
configuracion necesaria, generar los archivos de entorno en ~/.odev/projects/<name>/
y registrar el proyecto en el registro global.
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from typing import Any

import questionary
import typer
from rich.panel import Panel

from odev import __version__
from odev.commands._wizards import (
    MAPEO_VERSION_PG,
    VERSIONES_ODOO,
    preguntar_configuracion_base,
    renderizar_templates,
    valores_configuracion_por_defecto,
)
from odev.core.config import construir_addon_mounts, generate_odoo_conf
from odev.core.console import console, error, info, success, warning
from odev.core.detect import RepoLayout, TipoRepo, detectar_layout
from odev.core.ports import sugerir_puertos
from odev.core.registry import PROJECTS_DIR, Registry, RegistryEntry

# -- Constantes ----------------------------------------------------------------

# Templates a renderizar y su ruta destino relativa al directorio de config
_MAPA_TEMPLATES: list[tuple[str, str]] = [
    ("docker-compose.yml.j2", "docker-compose.yml"),
    ("entrypoint.sh.j2", "entrypoint.sh"),
    ("env.j2", ".env"),
    ("odev.yaml.j2", "odev.yaml"),
]


# -- Comando principal ----------------------------------------------------------


def adopt(
    directorio: str = typer.Argument(
        ".",
        help="Directorio del proyecto Odoo existente.",
    ),
    name: str = typer.Option(
        None,
        "--name",
        "-n",
        help="Nombre del proyecto (por defecto: nombre del directorio).",
    ),
    odoo_version: str = typer.Option(
        None,
        "--odoo-version",
        help="Version de Odoo (ej: 19.0, 18.0, 17.0).",
    ),
    no_interactive: bool = typer.Option(
        False,
        "--no-interactive",
        help="Modo no-interactivo (usar valores por defecto).",
    ),
) -> None:
    """Adopta un proyecto Odoo existente para gestionarlo con odev."""

    # 1. Resolver directorio ---------------------------------------------------
    ruta = Path(directorio).resolve()
    if not ruta.is_dir():
        error(f"'{ruta}' no es un directorio valido.")
        raise typer.Exit(1)

    # 2. Verificar si ya es un proyecto odev -----------------------------------
    if (ruta / ".odev.yaml").exists():
        error(
            f"'{ruta}' ya es un proyecto odev (tiene .odev.yaml). "
            "Usa 'odev up' directamente."
        )
        raise typer.Exit(1)

    # 3. Detectar layout -------------------------------------------------------
    layout = detectar_layout(ruta)

    if layout.tipo == TipoRepo.ODOO_FUENTE:
        error(
            "Detectado repositorio Odoo fuente completo (odoo-bin). "
            "Este tipo de proyecto no esta soportado aun."
        )
        raise typer.Exit(1)

    if layout.tipo == TipoRepo.DESCONOCIDO:
        warning("No se detectaron modulos Odoo en este directorio.")
        if no_interactive:
            raise typer.Exit(1)
        continuar = questionary.confirm(
            "Continuar de todos modos?",
            default=False,
        ).ask()
        if not continuar:
            raise typer.Exit()

    # 4. Mostrar resultados de deteccion ---------------------------------------
    _mostrar_deteccion(layout)

    # 5. Recopilar nombre del proyecto -----------------------------------------
    if name is None:
        if no_interactive:
            name = ruta.name
        else:
            name = questionary.text(
                "Nombre del proyecto:",
                default=ruta.name,
                validate=lambda val: (
                    len(val.strip()) > 0 or "El nombre del proyecto no puede estar vacio"
                ),
            ).ask()
            if name is None:
                raise typer.Exit()

    # 6. Verificar disponibilidad en el registro --------------------------------
    registro = Registry()
    existente = registro.obtener(name)
    if existente:
        error(f"Ya existe un proyecto '{name}' en el registro.")
        raise typer.Exit(1)

    # 7. Recopilar version de Odoo ---------------------------------------------
    if odoo_version is None:
        if no_interactive:
            odoo_version = "19.0"
        else:
            odoo_version = questionary.select(
                "Version de Odoo:",
                choices=VERSIONES_ODOO,
                default="19.0",
            ).ask()
            if odoo_version is None:
                raise typer.Exit()

    # 8. Recopilar configuracion adicional -------------------------------------
    puertos = sugerir_puertos()

    if not no_interactive:
        valores_extra = preguntar_configuracion_base(puertos)
    else:
        valores_extra = valores_configuracion_por_defecto(puertos)

    # 9. Crear directorio de configuracion -------------------------------------
    directorio_config = PROJECTS_DIR / name
    directorio_config.mkdir(parents=True, exist_ok=True)
    (directorio_config / "config").mkdir(exist_ok=True)
    (directorio_config / "logs").mkdir(exist_ok=True)
    (directorio_config / "snapshots").mkdir(exist_ok=True)

    # 10. Construir valores de template y renderizar ---------------------------
    valores = _construir_valores(
        nombre=name,
        ruta=ruta,
        layout=layout,
        odoo_version=odoo_version,
        directorio_config=directorio_config,
        puertos=puertos,
        extras=valores_extra,
    )

    # 11. Renderizar templates al directorio de config -------------------------
    info(f"Generando configuracion en {directorio_config}...")
    renderizar_templates(directorio_config, valores, _MAPA_TEMPLATES)

    # Hacer entrypoint.sh ejecutable
    ruta_entrypoint = directorio_config / "entrypoint.sh"
    if ruta_entrypoint.exists():
        os.chmod(ruta_entrypoint, 0o755)
        success("entrypoint.sh marcado como ejecutable")

    # Generar odoo.conf
    addon_mounts = valores["addon_mounts"]
    generate_odoo_conf(
        env_values=_extraer_env_values(valores),
        config_dir=directorio_config / "config",
        addon_mounts=addon_mounts,
        enterprise_enabled=valores.get("enterprise_enabled", False),
    )
    success("config/odoo.conf")

    # 12. Registrar en el registro global --------------------------------------
    entry = RegistryEntry(
        nombre=name,
        directorio_trabajo=ruta,
        directorio_config=directorio_config,
        modo="external",
        version_odoo=odoo_version,
        fecha_creacion=date.today().isoformat(),
    )
    registro.registrar(entry)
    success(f"Proyecto '{name}' registrado en el registro global.")

    # 13. Mostrar resumen ------------------------------------------------------
    _mostrar_resumen(name, ruta, directorio_config, layout, odoo_version, puertos)


# -- Funciones auxiliares -------------------------------------------------------


def _mostrar_deteccion(layout: RepoLayout) -> None:
    """Muestra los resultados de la deteccion de layout.

    Args:
        layout: Resultado del analisis de layout.
    """
    info(f"Tipo de repositorio: {layout.tipo.value}")
    info(f"Modulos encontrados: {layout.modulos_encontrados}")
    info(f"Submodulos git: {'Si' if layout.tiene_submodulos else 'No'}")
    info(f"Enterprise: {'Si' if layout.tiene_enterprise else 'No'}")
    info(f"Directorios de addons: {len(layout.rutas_addons)}")
    for ruta_addon in layout.rutas_addons:
        console.print(f"  [dim]•[/dim] {ruta_addon}")



def _construir_valores(
    *,
    nombre: str,
    ruta: Path,
    layout: RepoLayout,
    odoo_version: str,
    directorio_config: Path,
    puertos: dict[str, int],
    extras: dict[str, Any],
) -> dict[str, Any]:
    """Construye el diccionario unificado de valores para renderizar templates.

    Args:
        nombre: Nombre del proyecto.
        ruta: Ruta al directorio de trabajo del proyecto.
        layout: Resultado de la deteccion de layout.
        odoo_version: Version de Odoo seleccionada.
        directorio_config: Directorio de configuracion de odev.
        puertos: Puertos sugeridos.
        extras: Valores adicionales del wizard o por defecto.

    Returns:
        Diccionario con todas las claves necesarias para renderizar templates.
    """
    tag_imagen_odoo = odoo_version.replace(".0", "")
    tag_imagen_db = MAPEO_VERSION_PG.get(odoo_version, "16")

    # Construir addon mounts a partir de las rutas detectadas
    rutas_addons_str = [str(r) for r in layout.rutas_addons]
    addon_mounts = construir_addon_mounts(rutas_addons_str, directorio_config)

    # Determinar ruta enterprise
    if layout.tiene_enterprise:
        enterprise_path = str(ruta / "enterprise")
    else:
        enterprise_path = "./enterprise"

    habilitar_debugpy = extras.get("habilitar_debugpy", False)

    return {
        # --- Variables MAYUSCULAS (para env.j2, odoo.conf.j2) ---
        "PROJECT_NAME": nombre,
        "ODOO_VERSION": odoo_version,
        "ODOO_IMAGE_TAG": tag_imagen_odoo,
        "WEB_PORT": extras["web_port"],
        "PGWEB_PORT": extras["pgweb_port"],
        "DB_NAME": extras["db_name"],
        "DB_USER": extras["db_user"],
        "DB_PASSWORD": extras["db_password"],
        "DB_IMAGE_TAG": tag_imagen_db,
        "DB_PORT": str(puertos["DB_PORT"]),
        "DB_HOST": "db",
        "LOAD_LANGUAGE": extras["idioma"],
        "WITHOUT_DEMO": extras["sin_demo"],
        "DEBUGPY": "True" if habilitar_debugpy else "False",
        "DEBUGPY_PORT": str(puertos["DEBUGPY_PORT"]),
        "ADMIN_PASSWORD": "admin",
        "INIT_MODULES": "",
        "MAILHOG_PORT": str(puertos["MAILHOG_PORT"]),
        # --- Variables snake_case (para odev.yaml.j2, docker-compose.yml.j2) ---
        "project_name": nombre,
        "project_mode": "external",
        "working_dir": str(ruta),
        "odoo_version": odoo_version,
        "odoo_image_tag": tag_imagen_odoo,
        "odoo_image": f"odoo:{tag_imagen_odoo}",
        "db_image_tag": tag_imagen_db,
        "db_image": f"pgvector/pgvector:pg{tag_imagen_db}",
        "enterprise_enabled": layout.tiene_enterprise,
        "enterprise_path": enterprise_path,
        "addon_mounts": addon_mounts,
        "addon_container_paths": [m["container_path"] for m in addon_mounts],
        "addon_dirs_container": [m["container_path"] for m in addon_mounts],
        "addons_paths_list": rutas_addons_str,
        "odev_min_version": "0.2.0",
        "odev_version": __version__,
        "services_pgweb": extras.get("habilitar_pgweb", True),
        "services_mailhog": True,
        "project_description": "",
    }


def _extraer_env_values(valores: dict[str, Any]) -> dict[str, str]:
    """Extrae las variables de entorno (MAYUSCULAS) del dict de valores.

    generate_odoo_conf espera un dict con las claves MAYUSCULAS del .env.

    Args:
        valores: Diccionario completo de valores de template.

    Returns:
        Diccionario filtrado con solo las variables de entorno.
    """
    claves_env = {
        "PROJECT_NAME", "ODOO_VERSION", "ODOO_IMAGE_TAG", "WEB_PORT",
        "PGWEB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD", "DB_IMAGE_TAG",
        "DB_PORT", "DB_HOST", "LOAD_LANGUAGE", "WITHOUT_DEMO", "DEBUGPY",
        "DEBUGPY_PORT", "ADMIN_PASSWORD", "INIT_MODULES", "MAILHOG_PORT",
    }
    return {k: str(v) for k, v in valores.items() if k in claves_env}



def _mostrar_resumen(
    nombre: str,
    ruta: Path,
    directorio_config: Path,
    layout: RepoLayout,
    odoo_version: str,
    puertos: dict[str, int],
) -> None:
    """Muestra el resumen final del proyecto adoptado.

    Args:
        nombre: Nombre del proyecto.
        ruta: Directorio de trabajo del proyecto.
        directorio_config: Directorio de configuracion de odev.
        layout: Resultado de la deteccion de layout.
        odoo_version: Version de Odoo seleccionada.
        puertos: Puertos asignados al proyecto.
    """
    success(f"Proyecto '{nombre}' adoptado exitosamente.")
    console.print(Panel(
        f"[bold]Directorio de trabajo:[/bold] {ruta}\n"
        f"[bold]Configuracion:[/bold] {directorio_config}\n"
        f"[bold]Odoo:[/bold] {odoo_version}\n"
        f"[bold]Addons:[/bold] {len(layout.rutas_addons)} directorios\n"
        f"[bold]Puerto web:[/bold] {puertos['WEB_PORT']}\n\n"
        f"Para iniciar: [bold green]odev up[/bold green]",
        title="Proyecto adoptado",
        border_style="green",
    ))
