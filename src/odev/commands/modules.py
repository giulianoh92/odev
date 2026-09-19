"""Comando 'modules': lista modulos instalados del proyecto Odoo.

Consulta ir_module_module via psql y retorna la lista de modulos
en estado 'installed', 'to upgrade' o 'to install'.

Por default muestra una tabla Rich ordenada por nombre (D1). Con --json/-j
emite JSON sin formato:
  [{"name": str, "state": str, "version": str}, ...]
  Sin modulos: []
  Error de proyecto: exit 1

Nota: dependencias (ir_module_module_dependency) diferidas a 0.6.0
para evitar N+1 en catalogos grandes.
"""

from __future__ import annotations

import json
import sys

import typer
from rich.table import Table

from odev.commands._helpers import (
    obtener_docker,
    obtener_rutas,
    requerir_proyecto,
)
from odev.core.config import load_env
from odev.core.console import console, error, info

# SQL para obtener modulos instalados/pendientes.
# COALESCE convierte NULL en cadena vacia para version.
_SQL_MODULES = (
    "SELECT name, state, COALESCE(latest_version, '') AS version "
    "FROM ir_module_module "
    "WHERE state IN ('installed', 'to upgrade', 'to install') "
    "ORDER BY name"
)

# ASCII Unit Separator — mismo separador que sql --json
_FIELD_SEP = "\x1f"


def _parse_modules_output(raw: bytes) -> list[dict[str, str]]:
    """Parsea salida de psql en formato ASCII US a lista de modulos.

    Args:
        raw: Bytes capturados de psql con separador 0x1F.

    Returns:
        Lista de dicts con name, state, version.
    """
    text = raw.decode("utf-8", errors="replace")
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(_FIELD_SEP)
        if len(parts) >= 3:
            rows.append(
                {
                    "name": parts[0],
                    "state": parts[1],
                    "version": parts[2],
                }
            )
        elif len(parts) == 2:
            rows.append(
                {
                    "name": parts[0],
                    "state": parts[1],
                    "version": "",
                }
            )
    return rows


def _execute_modules(contexto) -> list[dict]:
    """Pure data-return. No I/O, no exits. MCP-callable.

    Queries installed Odoo modules via psql and returns structured list.

    Args:
        contexto: Resolved ProjectContext.

    Returns:
        List of {name, state, version} dicts.

    Raises:
        RuntimeError: If psql returns non-zero exit code.
    """
    rutas = obtener_rutas(contexto)
    valores_env = load_env(rutas.env_file)
    nombre_bd = valores_env.get("DB_NAME", "odoo_db")
    usuario_bd = valores_env.get("DB_USER", "odoo")

    args = [
        "psql",
        "-U",
        usuario_bd,
        "-d",
        nombre_bd,
        "-t",
        "-A",
        f"-F{_FIELD_SEP}",
        "-c",
        _SQL_MODULES,
    ]

    dc = obtener_docker(contexto)
    stdout, stderr, returncode = dc.exec_capture("db", args)

    if returncode != 0:
        first_err = stderr.decode("utf-8", errors="replace").splitlines()
        first_err_line = first_err[0].strip() if first_err else "Error en psql"
        raise RuntimeError(first_err_line)

    return _parse_modules_output(stdout)


def modules(
    json_output: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Emite JSON a stdout para consumo por agentes.",
    ),
) -> None:
    """Lista modulos instalados del proyecto Odoo.

    Consulta ir_module_module para modulos en estado 'installed',
    'to upgrade' o 'to install'. Por default muestra una tabla Rich
    ordenada por nombre; con --json/-j emite un array JSON sin formato (D1).

    Nota: las dependencias entre modulos no se incluyen todavia.

    Codigos de salida:

      0  Consulta exitosa (puede ser lista vacia [] o tabla vacia)

      1  Error: sin proyecto odev, DB no disponible, psql fallo
    """
    from odev.main import obtener_nombre_proyecto

    if json_output:
        try:
            # silencioso=True: requerir_proyecto no imprime su propio
            # diagnostico human-formatted. Este bloque arma el unico
            # diagnostico que un consumidor --json puede parsear (T6).
            contexto = requerir_proyecto(obtener_nombre_proyecto(), silencioso=True)
        except typer.Exit:
            err_msg = "No se encontro un proyecto odev en el directorio actual."
            sys.stderr.write(json.dumps({"error": err_msg}) + "\n")
            raise

        try:
            result = _execute_modules(contexto)
        except RuntimeError as e:
            sys.stderr.write(json.dumps({"error": str(e)}) + "\n")
            raise typer.Exit(1) from e

        sys.stdout.write(json.dumps(result) + "\n")
        raise typer.Exit(0)

    # Rich path (default): tabla human-readable, igual estilo que status.py.
    contexto = requerir_proyecto(obtener_nombre_proyecto())

    try:
        result = _execute_modules(contexto)
    except RuntimeError as e:
        error(str(e))
        raise typer.Exit(1) from e

    if not result:
        info("No se encontraron modulos instalados.")
        return

    tabla = Table(title="Modulos instalados")
    tabla.add_column("Nombre", style="cyan")
    tabla.add_column("Estado", style="bold")
    tabla.add_column("Version", style="dim")

    for modulo in result:
        estado = modulo["state"]
        estilo_estado = "green" if estado == "installed" else "yellow"
        tabla.add_row(
            modulo["name"],
            f"[{estilo_estado}]{estado}[/]",
            modulo["version"],
        )

    console.print(tabla)
