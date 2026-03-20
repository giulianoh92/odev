"""Comando 'down': detiene y elimina los contenedores del proyecto.

Corrige el bug del viejo CLI donde 'down' ejecutaba 'docker compose stop'
en lugar de 'docker compose down'. Ahora ejecuta correctamente 'down',
lo que detiene Y elimina los contenedores.
"""

import typer

from odev.commands._helpers import obtener_docker, requerir_proyecto
from odev.core.console import success


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
    from odev.main import obtener_nombre_proyecto
    contexto = requerir_proyecto(obtener_nombre_proyecto())
    dc = obtener_docker(contexto)
    dc.down(volumes=volumes)
    success("Entorno detenido.")
