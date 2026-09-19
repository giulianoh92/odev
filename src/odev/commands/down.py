"""Comando 'down': detiene y elimina los contenedores del proyecto.

Corrige el bug del viejo CLI donde 'down' ejecutaba 'docker compose stop'
en lugar de 'docker compose down'. Ahora ejecuta correctamente 'down',
lo que detiene Y elimina los contenedores.
"""

import typer

from odev.commands._helpers import obtener_docker, requerir_proyecto
from odev.core.console import info, success, warning


def down(
    volumes: bool = typer.Option(
        False,
        "-v",
        "--volumes",
        help="Tambien eliminar volumenes de datos.",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Saltar la confirmacion interactiva. Util para uso en agentes/CI.",
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

    Sin -v/--volumes, esta operacion NO es destructiva: solo detiene y
    elimina los contenedores, sin ningun prompt. Con -v/--volumes tambien
    se eliminan los volumenes de datos (base de datos y filestore), que es
    irreversible: pide confirmacion antes de proceder, salvo que se pase
    --yes.
    """
    from odev.main import obtener_nombre_proyecto

    contexto = requerir_proyecto(obtener_nombre_proyecto())
    dc = obtener_docker(contexto)

    if dry_run:
        info(f"Se ejecutaria: docker compose down{' -v' if volumes else ''}")
        info("  - Detendria y eliminaria los contenedores del proyecto.")
        if volumes:
            info("  - Eliminaria los volumenes de datos asociados (base de datos y filestore).")
        return

    if volumes:
        warning(
            f"Esto ELIMINARA los volumenes de datos del proyecto '{contexto.nombre}' "
            "(base de datos y filestore)!"
        )
        if not yes:
            confirmacion = typer.confirm("Estas seguro?", default=False)
            if not confirmacion:
                info("Operacion cancelada.")
                raise typer.Exit()

    dc.down(volumes=volumes)
    success("Entorno detenido.")
