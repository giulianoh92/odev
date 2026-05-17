"""Comando 'logs': muestra los logs de los servicios del proyecto.

Permite seguir los logs en tiempo real de un servicio especifico
(web, db) o de todos los servicios.

En 0.5.1 se agrego: --json/-j flag para capturar snapshot de logs como
array JSON (implica no-follow). --follow/-f flag para conflicto mutuo.
"""

from __future__ import annotations

import json
import re
import sys
from typing import Optional

import typer

from odev.commands._helpers import obtener_docker, requerir_proyecto

# Regex para parsear lineas de docker compose logs con timestamps:
#   "web  | 2024-01-01T00:00:00.000000000Z <rest>"
LINE_RE = re.compile(
    r"^(?P<svc>[^|]+?)\s*\|\s*(?P<ts>\S+)\s+(?P<rest>.*)$"
)

# Regex para extraer nivel de log de Odoo:
#   "<pid> <uid> INFO <logger> <message>"
ODOO_LEVEL_RE = re.compile(
    r"^\d+\s+\d+\s+(?P<level>INFO|WARNING|ERROR|DEBUG|CRITICAL)\s+(?P<msg>.*)$"
)


def _parse_logs(raw: str) -> list[dict]:
    """Parse raw docker compose log output into structured entries.

    Each physical line becomes one JSON entry. Lines that don't match the
    docker compose log format are skipped (defensive). Multi-line tracebacks
    produce N entries each with level: null (documented behavior, C2-S9).

    Args:
        raw: Raw string from docker compose logs --timestamps --no-color.

    Returns:
        List of dicts with keys: service, timestamp, level (str|null), message.
    """
    entries = []
    for line in raw.splitlines():
        m = LINE_RE.match(line)
        if not m:
            continue
        svc = m.group("svc").strip()
        ts = m.group("ts")
        rest = m.group("rest")

        # Try to extract Odoo log level from the rest of the line
        odoo_m = ODOO_LEVEL_RE.match(rest)
        if odoo_m:
            level: str | None = odoo_m.group("level")
            message = odoo_m.group("msg")
        else:
            level = None
            message = rest

        entries.append(
            {
                "service": svc,
                "timestamp": ts,
                "level": level,
                "message": message,
            }
        )
    return entries


def logs(
    service: str = typer.Argument(
        "web",
        help="Servicio del cual ver logs (web, db, o all para todos).",
    ),
    tail: int = typer.Option(
        100,
        "--tail",
        "-n",
        help="Cantidad de lineas a mostrar desde el final.",
    ),
    no_follow: bool = typer.Option(
        False,
        "--no-follow",
        help="No seguir la salida de logs en tiempo real.",
    ),
    follow: Optional[bool] = typer.Option(  # noqa: UP007
        None,
        "--follow",
        "-f",
        help="Seguir la salida de logs en tiempo real (conflicto con --json).",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Emite los logs como array JSON en stdout (implica no-follow).",
    ),
) -> None:
    """Muestra y sigue los logs de los servicios del proyecto.

    Por defecto muestra los logs del servicio 'web'. Usa 'all' para
    ver los logs de todos los servicios simultaneamente.

    Con --json, captura un snapshot de los ultimos N logs (--tail) y los
    emite como array JSON a stdout. --json y --follow son mutuamente
    excluyentes.
    """
    from odev.main import obtener_nombre_proyecto

    # Mutual exclusion: --json + --follow -> exit 2
    if json_output and follow:
        sys.stderr.write(
            json.dumps({"error": "--json and --follow are mutually exclusive"}) + "\n"
        )
        raise typer.Exit(2)

    contexto = requerir_proyecto(obtener_nombre_proyecto())
    dc = obtener_docker(contexto)

    if json_output:
        # Validate service exists (service="all" is not valid in JSON mode)
        servicios_conocidos = {s.get("Service") for s in dc.ps_parsed()}
        if service not in servicios_conocidos:
            sys.stderr.write(
                json.dumps({"error": f"Unknown service: {service}"}) + "\n"
            )
            raise typer.Exit(2)

        raw = dc.logs_capture(service, tail=tail)
        entries = _parse_logs(raw)
        sys.stdout.write(json.dumps(entries) + "\n")
        return

    # Default Rich/streaming path — unchanged from 0.5.0
    servicio = None if service == "all" else service
    dc.logs(service=servicio, follow=not no_follow, tail=tail)
