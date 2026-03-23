"""Funciones compartidas de wizard para los comandos init y adopt.

Contiene las constantes de versiones, las preguntas de configuracion
base comunes a ambos wizards, y la logica de renderizado de templates
Jinja2.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import questionary
import typer
from jinja2 import Environment, FileSystemLoader

from odev.core.console import success, warning
from odev.core.paths import get_project_templates_dir

# -- Constantes ----------------------------------------------------------------

VERSIONES_ODOO: list[str] = ["19.0", "18.0", "17.0", "16.0"]
"""Versiones de Odoo soportadas por el wizard (mas reciente primero)."""

MAPEO_VERSION_PG: dict[str, str] = {
    "19.0": "16",
    "18.0": "16",
    "17.0": "15",
    "16.0": "15",
}
"""Mapeo de version de Odoo a tag de imagen PostgreSQL recomendada."""


# -- Preguntas de configuracion base -------------------------------------------


def preguntar_configuracion_base(puertos: dict[str, int]) -> dict[str, Any]:
    """Ejecuta las preguntas de configuracion comunes a init y adopt.

    Pregunta al usuario por puerto web, puerto pgweb, nombre de BD,
    usuario de BD, password de BD, idioma, datos de demo, debugpy y pgweb.

    Argumentos:
        puertos: Puertos sugeridos por sugerir_puertos().

    Retorna:
        Diccionario con las claves: web_port, pgweb_port, db_name,
        db_user, db_password, idioma, sin_demo, habilitar_debugpy,
        habilitar_pgweb.
    """
    # Puerto web
    puerto_web = questionary.text(
        f"Puerto de Odoo ({puertos['WEB_PORT']}):",
        default=str(puertos["WEB_PORT"]),
    ).ask()
    if puerto_web is None:
        raise typer.Exit()

    # Puerto pgweb
    puerto_pgweb = questionary.text(
        f"Puerto de pgweb ({puertos['PGWEB_PORT']}):",
        default=str(puertos["PGWEB_PORT"]),
    ).ask()
    if puerto_pgweb is None:
        raise typer.Exit()

    # Base de datos
    nombre_db = questionary.text(
        "Nombre de la base de datos:",
        default="odoo_db",
    ).ask()
    if nombre_db is None:
        raise typer.Exit()

    usuario_db = questionary.text(
        "Usuario de la base de datos:",
        default="odoo",
    ).ask()
    if usuario_db is None:
        raise typer.Exit()

    password_db = questionary.text(
        "Contraseña de la base de datos:",
        default="odoo",
    ).ask()
    if password_db is None:
        raise typer.Exit()

    # Idioma
    idioma = questionary.text(
        "Idioma por defecto (ej. en_US, es_AR, fr_FR):",
        default="en_US",
    ).ask()
    if idioma is None:
        raise typer.Exit()

    # Datos de demo
    sin_demo = questionary.select(
        "Datos de demo:",
        choices=[
            questionary.Choice("Omitir datos de demo", value="all"),
            questionary.Choice("Cargar datos de demo", value=""),
        ],
        default="all",
    ).ask()
    if sin_demo is None:
        raise typer.Exit()

    # Debugpy
    habilitar_debugpy = questionary.confirm(
        "Habilitar debugpy para depuracion remota?",
        default=False,
    ).ask()
    if habilitar_debugpy is None:
        raise typer.Exit()

    # pgweb
    habilitar_pgweb = questionary.confirm(
        "Habilitar pgweb?",
        default=True,
    ).ask()
    if habilitar_pgweb is None:
        raise typer.Exit()

    return {
        "web_port": puerto_web,
        "pgweb_port": puerto_pgweb,
        "db_name": nombre_db,
        "db_user": usuario_db,
        "db_password": password_db,
        "idioma": idioma,
        "sin_demo": sin_demo,
        "habilitar_debugpy": habilitar_debugpy,
        "habilitar_pgweb": habilitar_pgweb,
    }


def valores_configuracion_por_defecto(puertos: dict[str, int]) -> dict[str, Any]:
    """Genera valores por defecto de configuracion base (modo no-interactivo).

    Retorna el mismo diccionario que preguntar_configuracion_base() pero
    con valores por defecto sin preguntar al usuario.

    Argumentos:
        puertos: Puertos sugeridos por sugerir_puertos().

    Retorna:
        Diccionario con las mismas claves que preguntar_configuracion_base().
    """
    return {
        "web_port": str(puertos["WEB_PORT"]),
        "pgweb_port": str(puertos["PGWEB_PORT"]),
        "db_name": "odoo_db",
        "db_user": "odoo",
        "db_password": "odoo",
        "idioma": "en_US",
        "sin_demo": "all",
        "habilitar_debugpy": False,
        "habilitar_pgweb": True,
    }


# -- Renderizado de templates --------------------------------------------------


def renderizar_templates(
    directorio: Path,
    valores: dict[str, Any],
    mapa_templates: list[tuple[str, str]],
    archivos_regenerables: set[str] | None = None,
) -> None:
    """Renderiza templates Jinja2 y los escribe en el directorio destino.

    Combina la logica de renderizado usada por init y adopt. Si se pasa
    archivos_regenerables, sobreescribe esos archivos aunque ya existan;
    el resto se omite si ya existe.

    Argumentos:
        directorio: Directorio donde escribir los archivos generados.
        valores: Diccionario de valores para renderizar los templates.
        mapa_templates: Lista de tuplas (nombre_template, ruta_relativa_destino).
        archivos_regenerables: Conjunto de rutas relativas que se sobreescriben
            siempre. Si es None, nunca se sobreescribe (comportamiento de adopt).
    """
    entorno_jinja = Environment(
        loader=FileSystemLoader(str(get_project_templates_dir())),
        keep_trailing_newline=True,
    )

    for nombre_template, ruta_relativa_destino in mapa_templates:
        ruta_destino = directorio / ruta_relativa_destino
        es_regenerable = (
            archivos_regenerables is not None
            and ruta_relativa_destino in archivos_regenerables
        )

        if ruta_destino.exists() and not es_regenerable:
            if archivos_regenerables is not None:
                # Solo mostrar advertencia cuando el concepto de regenerables existe (init)
                warning(f"Archivo existente, se omite: {ruta_relativa_destino}")
            continue

        # Asegurar que el directorio padre exista
        ruta_destino.parent.mkdir(parents=True, exist_ok=True)

        # Renderizar template
        template = entorno_jinja.get_template(nombre_template)
        contenido = template.render(**valores)
        ruta_destino.write_text(contenido)

        if es_regenerable and ruta_destino.exists():
            success(f"{ruta_relativa_destino} (regenerado)")
        else:
            success(ruta_relativa_destino)
