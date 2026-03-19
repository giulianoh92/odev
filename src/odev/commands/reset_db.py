"""Comando 'reset-db': destruye la base de datos y volumenes, reinicia desde cero.

Ejecuta docker compose down -v para eliminar contenedores y volumenes,
luego levanta el entorno nuevamente para empezar con una base de datos limpia.
"""

import typer

from odev.core.console import error, info, success, warning
from odev.core.docker import DockerCompose
from odev.core.paths import ProjectPaths


def reset_db() -> None:
    """Destruye la base de datos y volumenes, luego reinicia el entorno desde cero.

    Pide confirmacion antes de proceder ya que esta operacion es destructiva
    e irreversible. Elimina todos los volumenes de datos incluyendo la
    base de datos y el filestore.
    """
    try:
        rutas = ProjectPaths()
    except FileNotFoundError:
        error("No se encontro un proyecto odev. Ejecuta 'odev init' para crear uno.")
        raise typer.Exit(1)

    warning("Esto ELIMINARA la base de datos y TODOS los datos!")
    confirmacion = typer.confirm("Estas seguro?", default=False)
    if not confirmacion:
        info("Operacion cancelada.")
        raise typer.Exit()

    dc = DockerCompose(rutas.root)

    info("Deteniendo contenedores y eliminando volumenes...")
    dc.down(volumes=True)

    info("Iniciando entorno limpio...")
    dc.up()

    success("Base de datos reiniciada. El entorno limpio esta iniciando.")
