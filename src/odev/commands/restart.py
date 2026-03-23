"""Comando 'restart': reinicia un servicio del stack Docker."""

import typer

from odev.commands._helpers import obtener_docker, requerir_proyecto
from odev.core.console import info, success


def restart(
    service: str = typer.Argument(
        "web",
        help="Servicio a reiniciar (web, db, pgweb, mailhog).",
    ),
) -> None:
    """Reinicia un servicio del stack Docker (por defecto: web)."""
    from odev.main import obtener_nombre_proyecto
    contexto = requerir_proyecto(obtener_nombre_proyecto())
    dc = obtener_docker(contexto)

    info(f"Reiniciando servicio {service}...")
    dc.restart(service)
    success(f"Servicio '{service}' reiniciado.")
