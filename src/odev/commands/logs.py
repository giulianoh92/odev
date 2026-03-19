"""Comando 'logs': muestra los logs de los servicios del proyecto.

Permite seguir los logs en tiempo real de un servicio especifico
(web, db) o de todos los servicios.
"""

import typer

from odev.core.console import error
from odev.core.docker import DockerCompose
from odev.core.paths import ProjectPaths


def logs(
    service: str = typer.Argument(
        "web",
        help="Servicio del cual ver logs (web, db, o all para todos).",
    ),
    tail: int = typer.Option(
        100,
        "--tail",
        "-n",
        help="Cantidad de lineas a mostrar desde el final.",
    ),
    no_follow: bool = typer.Option(
        False,
        "--no-follow",
        help="No seguir la salida de logs en tiempo real.",
    ),
) -> None:
    """Muestra y sigue los logs de los servicios del proyecto.

    Por defecto muestra los logs del servicio 'web'. Usa 'all' para
    ver los logs de todos los servicios simultaneamente.
    """
    try:
        rutas = ProjectPaths()
    except FileNotFoundError:
        error("No se encontro un proyecto odev. Ejecuta 'odev init' para crear uno.")
        raise typer.Exit(1)

    dc = DockerCompose(rutas.root)
    servicio = None if service == "all" else service
    dc.logs(service=servicio, follow=not no_follow, tail=tail)
