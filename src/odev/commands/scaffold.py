"""Comando 'scaffold': crea un nuevo modulo Odoo desde el template.

Genera la estructura completa de un modulo Odoo en el directorio
addons/ del proyecto, usando el template bundled en el paquete pip.
"""

import re
import shutil
from pathlib import Path

import typer

from odev.core.console import error, info, success
from odev.core.paths import ProjectPaths, get_module_template_dir


def scaffold(
    name: str = typer.Argument(
        ...,
        help="Nombre del nuevo modulo (snake_case).",
    ),
) -> None:
    """Crea un nuevo modulo Odoo desde el template.

    Valida que el nombre sea snake_case, copia el template bundled
    en el paquete al directorio addons/ del proyecto, y reemplaza
    los placeholders con el nombre del modulo.
    """
    # Validar nombre del modulo
    if not re.match(r"^[a-z][a-z0-9_]*$", name):
        error(
            "El nombre del modulo debe ser snake_case "
            "(letras minusculas, digitos, guiones bajos, comenzando con una letra)."
        )
        raise typer.Exit(1)

    try:
        rutas = ProjectPaths()
    except FileNotFoundError:
        error("No se encontro un proyecto odev. Ejecuta 'odev init' para crear uno.")
        raise typer.Exit(1)

    directorio_template = get_module_template_dir()
    if not directorio_template.exists():
        error(f"No se encontro el directorio de templates: {directorio_template}")
        raise typer.Exit(1)

    directorio_destino = rutas.addons_dir / name
    if directorio_destino.exists():
        error(f"El directorio del modulo ya existe: {directorio_destino}")
        raise typer.Exit(1)

    rutas.addons_dir.mkdir(parents=True, exist_ok=True)
    info(f"Creando modulo: {name}")

    # Copiar template al destino
    shutil.copytree(directorio_template, directorio_destino)

    # Reemplazar __module_name__ en nombres de archivos y contenido
    _reemplazar_en_arbol(directorio_destino, "__module_name__", name)

    success(f"Modulo creado: {directorio_destino}")
    info("Proximos pasos:")
    info(f"  1. Editar addons/{name}/__manifest__.py")
    info(f"  2. Reiniciar Odoo o ejecutar: odev update {name}")


def _reemplazar_en_arbol(raiz: Path, placeholder: str, reemplazo: str) -> None:
    """Reemplaza el placeholder en nombres de archivos y contenido bajo el directorio raiz.

    Hace dos pasadas:
    1. Reemplaza el placeholder en el contenido de todos los archivos.
    2. Renombra archivos y directorios que contengan el placeholder
       (del mas profundo al mas superficial para evitar conflictos).

    Args:
        raiz: Directorio raiz donde buscar.
        placeholder: Cadena a reemplazar.
        reemplazo: Cadena con la que reemplazar.
    """
    # Primera pasada: reemplazar contenido en archivos
    for ruta in sorted(raiz.rglob("*")):
        if ruta.is_file():
            try:
                contenido = ruta.read_text()
                if placeholder in contenido:
                    ruta.write_text(contenido.replace(placeholder, reemplazo))
            except UnicodeDecodeError:
                continue

    # Segunda pasada: renombrar archivos y directorios (del mas profundo al mas superficial)
    for ruta in sorted(raiz.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if placeholder in ruta.name:
            nuevo_nombre = ruta.name.replace(placeholder, reemplazo)
            ruta.rename(ruta.parent / nuevo_nombre)
