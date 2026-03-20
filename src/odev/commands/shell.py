"""Comando 'shell': abre un shell bash dentro del contenedor de Odoo.

Ejecuta una sesion interactiva de bash en el contenedor web,
permitiendo inspeccion directa del entorno.
"""

import typer

from odev.commands._helpers import obtener_docker, requerir_proyecto
from odev.core.console import info


def shell() -> None:
    """Abre un shell bash interactivo dentro del contenedor de Odoo.

    Detecta el proyecto actual y ejecuta /bin/bash de forma interactiva
    en el contenedor del servicio web.
    """
    from odev.main import obtener_nombre_proyecto
    contexto = requerir_proyecto(obtener_nombre_proyecto())

    info("Entrando al shell del contenedor Odoo...")
    dc = obtener_docker(contexto)
    dc.exec_cmd("web", ["/bin/bash"], interactive=True)
