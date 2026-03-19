"""Comando 'update': actualiza (upgrade) un modulo Odoo.

Ejecuta 'odoo -u <modulo>' dentro del contenedor web para actualizar
el modulo especificado y luego reinicia el servicio web.
"""

import typer

from odev.core.config import load_env
from odev.core.console import error, info, success
from odev.core.docker import DockerCompose
from odev.core.paths import ProjectPaths


def update(
    module: str = typer.Argument(
        ...,
        help="Nombre del modulo a actualizar.",
    ),
) -> None:
    """Actualiza (upgrade) un modulo Odoo y reinicia el servicio web.

    Ejecuta la actualizacion del modulo indicado en la base de datos
    configurada, deteniendo Odoo despues de la actualizacion, y luego
    reinicia el servicio web para aplicar los cambios.
    """
    try:
        rutas = ProjectPaths()
    except FileNotFoundError:
        error("No se encontro un proyecto odev. Ejecuta 'odev init' para crear uno.")
        raise typer.Exit(1)

    valores_env = load_env(rutas.env_file)
    nombre_bd = valores_env.get("DB_NAME", "odoo_db")

    dc = DockerCompose(rutas.root)

    info(f"Actualizando modulo: {module}")
    dc.exec_cmd(
        "web",
        ["odoo", "-u", module, "-d", nombre_bd, "--stop-after-init"],
        interactive=True,
    )

    info("Reiniciando servicio web...")
    dc.restart("web")
    success(f"Modulo '{module}' actualizado y servicio web reiniciado.")
