"""Comando 'addon-install': instala un modulo Odoo por primera vez.

Ejecuta 'odoo -i <modulo>' dentro del contenedor web para instalar
el modulo especificado y luego reinicia el servicio web.
"""

import typer

from odev.commands._helpers import obtener_docker, obtener_rutas, requerir_proyecto
from odev.core.config import load_env
from odev.core.console import info, success


def install(
    module: str = typer.Argument(
        ...,
        help="Nombre del modulo a instalar.",
    ),
) -> None:
    """Instala un modulo Odoo por primera vez y reinicia el servicio web.

    Ejecuta la instalacion del modulo indicado en la base de datos
    configurada, deteniendo Odoo despues de la instalacion, y luego
    reinicia el servicio web para aplicar los cambios.
    """
    from odev.main import obtener_nombre_proyecto
    contexto = requerir_proyecto(obtener_nombre_proyecto())
    rutas = obtener_rutas(contexto)

    valores_env = load_env(rutas.env_file)
    nombre_bd = valores_env.get("DB_NAME", "odoo_db")

    dc = obtener_docker(contexto)

    info(f"Instalando modulo: {module}")
    dc.exec_cmd(
        "web",
        ["odoo", "-i", module, "-d", nombre_bd, "--stop-after-init"],
        interactive=True,
    )

    info("Reiniciando servicio web...")
    dc.restart("web")
    success(f"Modulo '{module}' instalado y servicio web reiniciado.")
