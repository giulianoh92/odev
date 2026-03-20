"""Comando 'restart': reinicia el servicio web de Odoo.

Ejecuta docker compose restart sobre el servicio 'web' del proyecto actual.
"""

import typer

from odev.commands._helpers import obtener_docker, requerir_proyecto
from odev.core.console import info, success


def restart() -> None:
    """Reinicia el contenedor web de Odoo.

    Detecta el proyecto actual y reinicia el servicio web para
    aplicar cambios en el codigo o la configuracion.
    """
    from odev.main import obtener_nombre_proyecto
    contexto = requerir_proyecto(obtener_nombre_proyecto())

    info("Reiniciando servicio web...")
    dc = obtener_docker(contexto)
    dc.restart("web")
    success("Servicio web reiniciado.")
