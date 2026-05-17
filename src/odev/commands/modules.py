"""Comando 'modules': lista modulos instalados del proyecto Odoo.

Consulta ir_module_module via psql y retorna la lista de modulos
en estado 'installed', 'to upgrade' o 'to install'.

JSON schema (--json):
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

from odev.commands._helpers import (
    obtener_docker,
    obtener_rutas,
    requerir_proyecto,
)
from odev.core.config import load_env
from odev.core.resolver import ProyectoAmbiguoError, ProyectoNoEncontradoError

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
            rows.append({
                "name": parts[0],
                "state": parts[1],
                "version": parts[2],
            })
        elif len(parts) == 2:
            rows.append({
                "name": parts[0],
                "state": parts[1],
                "version": "",
            })
    return rows


def modules(
    json_output: bool = typer.Option(
        True,
        "--json",
        "-j",
        help=(
            "Emite JSON a stdout (default en 0.5.0). "
            "Output human-readable planificado para 0.6.0."
        ),
    ),
) -> None:
    """Lista modulos instalados del proyecto Odoo en formato JSON.

    Consulta ir_module_module para modulos en estado 'installed',
    'to upgrade' o 'to install'. Retorna JSON array ordenado por nombre.

    Nota: las dependencias entre modulos se incluiran en 0.6.0.

    Codigos de salida:

      0  Consulta exitosa (puede ser lista vacia [])

      1  Error: sin proyecto odev, DB no disponible, psql fallo
    """
    from odev.main import obtener_nombre_proyecto

    try:
        contexto = requerir_proyecto(obtener_nombre_proyecto())
    except (ProyectoNoEncontradoError, ProyectoAmbiguoError) as e:
        sys.stderr.write(json.dumps({"error": str(e)}) + "\n")
        raise typer.Exit(1) from e
    except typer.Exit:
        err_msg = "No se encontro un proyecto odev en el directorio actual."
        sys.stderr.write(json.dumps({"error": err_msg}) + "\n")
        raise

    rutas = obtener_rutas(contexto)
    valores_env = load_env(rutas.env_file)
    nombre_bd = valores_env.get("DB_NAME", "odoo_db")
    usuario_bd = valores_env.get("DB_USER", "odoo")

    args = [
        "psql",
        "-U", usuario_bd,
        "-d", nombre_bd,
        "-t",  # tuples only (sin header)
        "-A",  # unaligned
        f"-F{_FIELD_SEP}",  # field separator
        "-c", _SQL_MODULES,
    ]

    dc = obtener_docker(contexto)
    stdout, stderr, returncode = dc.exec_capture("db", args)

    if returncode != 0:
        first_err = stderr.decode("utf-8", errors="replace").splitlines()
        first_err_line = first_err[0].strip() if first_err else "Error en psql"
        sys.stderr.write(json.dumps({"error": first_err_line}) + "\n")
        raise typer.Exit(1)

    result = _parse_modules_output(stdout)
    sys.stdout.write(json.dumps(result) + "\n")
    raise typer.Exit(0)
