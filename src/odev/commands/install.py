"""Comando 'addon-install': instala un modulo Odoo por primera vez."""

import typer

from odev.commands._helpers import ejecutar_operacion_modulo


def install(
    module: str = typer.Argument(..., help="Nombre del modulo a instalar."),
) -> None:
    """Instala un modulo Odoo por primera vez y reinicia el servicio web."""
    ejecutar_operacion_modulo(module, "-i", "Instalando", "instalado")
