"""Comando 'py': evalua una expresion Python en odoo shell."""

from __future__ import annotations

import typer

from odev.commands._helpers import (
    ejecutar_passthrough,
    obtener_docker,
    obtener_rutas,
    requerir_proyecto,
)
from odev.core.config import load_env
from odev.core.console import error


def _run_py(expression: str) -> None:
    from odev.main import obtener_nombre_proyecto

    if not expression.strip():
        error("La expresion Python no puede estar vacia.")
        raise typer.Exit(2)

    contexto = requerir_proyecto(obtener_nombre_proyecto())
    rutas = obtener_rutas(contexto)
    valores_env = load_env(rutas.env_file)
    nombre_bd = valores_env.get("DB_NAME", "odoo_db")

    script = f"print({expression})\n".encode("utf-8")
    args = [
        "odoo",
        "shell",
        "--config=/etc/odoo/odoo.conf",
        "-d",
        nombre_bd,
        "--no-http",
    ]

    dc = obtener_docker(contexto)
    ejecutar_passthrough(dc, "web", args, stdin_data=script)


def py(
    expression: str = typer.Argument(
        ...,
        help=(
            "Expresion Python a evaluar en odoo shell. "
            "Cuidado: side-effects ORM (.create/.write) se commitean. "
            "El banner de Odoo puede aparecer en stdout (v1 — passthrough raw)."
        ),
    ),
) -> None:
    """Evalua una expresion en odoo shell y emite el resultado por stdout.

    Codigos de salida:

      0  Expresion evaluada sin errores

      1  Error en Odoo shell (excepcion Python, DB no disponible, etc.)

      2  Error de uso (expresion vacia)
    """
    _run_py(expression)
