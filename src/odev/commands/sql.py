"""Comando 'sql': ejecuta una consulta SQL no-interactiva en el contenedor db.

JSON schema (--json):
  [{"col1": "val1", "col2": "val2"}, ...]   rows returned
  []                                          zero rows
  stderr: {"error": "<psql stderr first line>"}  on psql error

Nota: los valores son strings (protocolo texto de psql). Usar CAST en SQL
para tipos numericos si se necesita precision de tipo en el resultado JSON.
--json y --csv son mutuamente excluyentes (exit 2 si se combinan).
"""

from __future__ import annotations

import json
import sys

import typer

from odev.commands._helpers import (
    ejecutar_passthrough,
    obtener_docker,
    obtener_rutas,
    requerir_proyecto,
)
from odev.core.config import load_env
from odev.core.console import error

# ASCII Unit Separator (0x1F) — separador de campos para psql JSON mode.
# Nunca aparece en datos SQL normales. Evita problemas de quoting en CSV.
_FIELD_SEP = "\x1f"


def _parse_psql_us_output(raw: bytes) -> list[dict[str, str]]:
    """Parsea salida de psql con delimitador ASCII Unit Separator.

    Primera linea = header con nombres de columnas.
    Lineas siguientes = filas de datos. Lineas vacias ignoradas.

    Args:
        raw: Salida raw de psql en bytes.

    Returns:
        Lista de diccionarios {columna: valor}.
    """
    text = raw.decode("utf-8", errors="replace")
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return []

    headers = lines[0].split(_FIELD_SEP)
    rows = []
    for line in lines[1:]:
        values = line.split(_FIELD_SEP)
        # Rellenar con cadenas vacias si la fila tiene menos columnas que el header
        while len(values) < len(headers):
            values.append("")
        rows.append(dict(zip(headers, values)))
    return rows


def _run_sql(query: str, csv: bool, json_output: bool = False) -> None:
    from odev.main import obtener_nombre_proyecto

    if not query.strip():
        error("La consulta SQL no puede estar vacia.")
        raise typer.Exit(2)

    if json_output and csv:
        error("--json y --csv son mutuamente excluyentes.")
        raise typer.Exit(2)

    contexto = requerir_proyecto(obtener_nombre_proyecto())
    rutas = obtener_rutas(contexto)
    valores_env = load_env(rutas.env_file)
    nombre_bd = valores_env.get("DB_NAME", "odoo_db")
    usuario_bd = valores_env.get("DB_USER", "odoo")

    if json_output:
        # Usar ASCII Unit Separator como delimitador + tuples-only para datos.
        # Ejecutar dos veces: una para el header, otra para los datos.
        # Mas eficiente: una sola ejecucion con header separado por \x1f.
        args = [
            "psql",
            "-U", usuario_bd,
            "-d", nombre_bd,
            "-c", query,
            "--no-align",
            f"--field-separator={_FIELD_SEP}",
            "--pset=footer=off",
        ]
        dc = obtener_docker(contexto)
        stdout, stderr, returncode = dc.exec_capture("db", args)

        if returncode != 0:
            first_err = stderr.decode("utf-8", errors="replace").splitlines()
            first_err_line = first_err[0].strip() if first_err else "Error desconocido en psql"
            sys.stderr.write(json.dumps({"error": first_err_line}) + "\n")
            raise typer.Exit(1)

        rows = _parse_psql_us_output(stdout)
        sys.stdout.write(json.dumps(rows) + "\n")
        raise typer.Exit(0)

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
    json_output: bool = typer.Option(
        False,
        "--json",
        "-j",
        help=(
            "Emite JSON a stdout. Valores son strings (protocolo texto psql). "
            "Usar CAST en SQL para precision de tipo. Mutuamente excluyente con --csv."
        ),
    ),
) -> None:
    """Ejecuta una consulta SQL via psql -c en el contenedor db.

    Codigos de salida:

      0  Consulta ejecutada sin errores

      1  Error de psql (SQL invalido, conexion fallida, etc.)

      2  Error de uso (query vacia, flags incompatibles)
    """
    _run_sql(query, csv, json_output)
