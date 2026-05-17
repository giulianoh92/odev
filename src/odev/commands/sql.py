"""Comando 'sql': ejecuta una consulta SQL no-interactiva en el contenedor db."""

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


def _run_sql(query: str, csv: bool) -> None:
    from odev.main import obtener_nombre_proyecto

    if not query.strip():
        error("La consulta SQL no puede estar vacia.")
        raise typer.Exit(2)

    contexto = requerir_proyecto(obtener_nombre_proyecto())
    rutas = obtener_rutas(contexto)
    valores_env = load_env(rutas.env_file)
    nombre_bd = valores_env.get("DB_NAME", "odoo_db")
    usuario_bd = valores_env.get("DB_USER", "odoo")

    args = ["psql", "-U", usuario_bd, "-d", nombre_bd, "-c", query]
    if csv:
        # Unaligned, tuples-only, comma field-sep — minimal CSV-ish output.
        # NOT real RFC 4180 CSV: no quoting/escaping for special chars.
        args.extend(["-A", "-t", "-F", ","])

    dc = obtener_docker(contexto)
    ejecutar_passthrough(dc, "db", args)


def sql(
    query: str = typer.Argument(..., help="Sentencia SQL a ejecutar (psql -c)."),
    csv: bool = typer.Option(
        False,
        "--csv",
        help="Salida estilo CSV (sin comillas/escape — uso interno).",
    ),
) -> None:
    """Ejecuta una consulta SQL via psql -c en el contenedor db.

    Codigos de salida:

      0  Consulta ejecutada sin errores

      1  Error de psql (SQL invalido, conexion fallida, etc.)

      2  Error de uso (query vacia)
    """
    _run_sql(query, csv)
