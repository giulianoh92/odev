"""Comando 'update': actualiza (upgrade) un modulo Odoo."""

import typer

from odev.commands._helpers import ejecutar_operacion_modulo


def update(
    module: str = typer.Argument(..., help="Nombre del modulo a actualizar."),
) -> None:
    """Actualiza (upgrade) un modulo Odoo y reinicia el servicio web."""
    ejecutar_operacion_modulo(module, "-u", "Actualizando", "actualizado")
