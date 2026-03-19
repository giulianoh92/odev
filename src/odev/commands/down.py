"""Comando 'down': detiene y elimina los contenedores del proyecto.

Corrige el bug del viejo CLI donde 'down' ejecutaba 'docker compose stop'
en lugar de 'docker compose down'. Ahora ejecuta correctamente 'down',
lo que detiene Y elimina los contenedores.
"""

import typer

from odev.core.console import error, success
from odev.core.docker import DockerCompose
from odev.core.paths import ProjectPaths


def down(
    volumes: bool = typer.Option(
        False,
        "-v",
        "--volumes",
        help="Tambien eliminar volumenes de datos.",
    ),
) -> None:
    """Detiene y elimina los contenedores del proyecto.

    Ejecuta 'docker compose down' sobre el proyecto detectado.
    Opcionalmente elimina los volumenes asociados con el flag -v.
    """
    try:
        rutas = ProjectPaths()
    except FileNotFoundError:
        error("No se encontro un proyecto odev. Ejecuta 'odev init' para crear uno.")
        raise typer.Exit(1)

    dc = DockerCompose(rutas.root)
    dc.down(volumes=volumes)
    success("Entorno detenido.")
