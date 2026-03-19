"""Comando 'restart': reinicia el servicio web de Odoo.

Ejecuta docker compose restart sobre el servicio 'web' del proyecto actual.
"""

import typer

from odev.core.console import error, info, success
from odev.core.docker import DockerCompose
from odev.core.paths import ProjectPaths


def restart() -> None:
    """Reinicia el contenedor web de Odoo.

    Detecta el proyecto actual y reinicia el servicio web para
    aplicar cambios en el codigo o la configuracion.
    """
    try:
        rutas = ProjectPaths()
    except FileNotFoundError:
        error("No se encontro un proyecto odev. Ejecuta 'odev init' para crear uno.")
        raise typer.Exit(1)

    info("Reiniciando servicio web...")
    dc = DockerCompose(rutas.root)
    dc.restart("web")
    success("Servicio web reiniciado.")
