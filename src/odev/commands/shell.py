"""Comando 'shell': abre una terminal dentro de un contenedor."""

import typer

from odev.commands._helpers import obtener_docker, requerir_proyecto
from odev.core.console import info


def shell(
    service: str = typer.Argument(
        "web",
        help="Servicio donde abrir la terminal (web, db).",
    ),
) -> None:
    """Abre una terminal bash dentro de un contenedor del stack."""
    from odev.main import obtener_nombre_proyecto
    contexto = requerir_proyecto(obtener_nombre_proyecto())
    dc = obtener_docker(contexto)

    info(f"Abriendo terminal en '{service}'...")
    dc.exec_cmd(service, ["bash"], interactive=True)
