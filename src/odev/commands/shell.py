"""Comando 'shell': abre un shell bash dentro del contenedor de Odoo.

Ejecuta una sesion interactiva de bash en el contenedor web,
permitiendo inspeccion directa del entorno.
"""

import typer

from odev.core.console import error, info
from odev.core.docker import DockerCompose
from odev.core.paths import ProjectPaths


def shell() -> None:
    """Abre un shell bash interactivo dentro del contenedor de Odoo.

    Detecta el proyecto actual y ejecuta /bin/bash de forma interactiva
    en el contenedor del servicio web.
    """
    try:
        rutas = ProjectPaths()
    except FileNotFoundError:
        error("No se encontro un proyecto odev. Ejecuta 'odev init' para crear uno.")
        raise typer.Exit(1)

    info("Entrando al shell del contenedor Odoo...")
    dc = DockerCompose(rutas.root)
    dc.exec_cmd("web", ["/bin/bash"], interactive=True)
