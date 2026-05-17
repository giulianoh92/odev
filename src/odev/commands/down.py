"""Comando 'down': detiene y elimina los contenedores del proyecto.

Corrige el bug del viejo CLI donde 'down' ejecutaba 'docker compose stop'
en lugar de 'docker compose down'. Ahora ejecuta correctamente 'down',
lo que detiene Y elimina los contenedores.
"""

import typer

from odev.commands._helpers import obtener_docker, requerir_proyecto
from odev.core.console import info, success


def down(
    volumes: bool = typer.Option(
        False,
        "-v",
        "--volumes",
        help="Tambien eliminar volumenes de datos.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Mostrar que se haria sin tocar los contenedores.",
    ),
) -> None:
    """Detiene y elimina los contenedores del proyecto.

    Ejecuta 'docker compose down' sobre el proyecto detectado.
    Opcionalmente elimina los volumenes asociados con la opcion -v.
    """
    from odev.main import obtener_nombre_proyecto

    contexto = requerir_proyecto(obtener_nombre_proyecto())
    dc = obtener_docker(contexto)

    if dry_run:
        info(f"Se ejecutaria: docker compose down{' -v' if volumes else ''}")
        info("  - Detendria y eliminaria los contenedores del proyecto.")
        if volumes:
            info("  - Eliminaria los volumenes de datos asociados.")
        return

    dc.down(volumes=volumes)
    success("Entorno detenido.")
