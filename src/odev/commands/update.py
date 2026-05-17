"""Comando 'update': actualiza (upgrade) uno o varios modulos Odoo."""

import typer

from odev.commands._helpers import (
    obtener_docker,
    obtener_rutas,
    parsear_modulos_csv,
    requerir_proyecto,
    validar_modulos,
)
from odev.core.config import load_env


def update(
    module: str = typer.Argument(
        ...,
        help=("Modulo(s) a actualizar. CSV soportado: 'm1,m2,m3'. 'all' solo como token unico."),
    ),
    no_validate: bool = typer.Option(
        False,
        "--no-validate",
        help="Omite la validacion previa contra addons-path.",
    ),
) -> None:
    """Actualiza (upgrade) modulo(s) Odoo y reinicia el servicio web."""
    from odev.main import obtener_nombre_proyecto

    contexto = requerir_proyecto(obtener_nombre_proyecto())
    modulos = parsear_modulos_csv(module)
    validar_modulos(modulos, contexto, no_validate=no_validate)

    rutas = obtener_rutas(contexto)
    valores_env = load_env(rutas.env_file)
    nombre_bd = valores_env.get("DB_NAME", "odoo_db")

    dc = obtener_docker(contexto)

    from odev.core.console import info, success

    modulos_csv = ",".join(modulos)
    info(f"Actualizando modulo(s): {modulos_csv}")
    dc.exec_cmd(
        "web",
        ["odoo", "-u", modulos_csv, "-d", nombre_bd, "--stop-after-init"],
        interactive=True,
    )

    info("Reiniciando servicio web...")
    dc.restart("web")
    success(f"Modulo(s) '{modulos_csv}' actualizado(s) y servicio web reiniciado.")
