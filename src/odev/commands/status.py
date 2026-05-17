"""Comando 'status': muestra el estado de los servicios del proyecto.

Presenta una tabla con informacion de cada servicio de Docker Compose
incluyendo nombre, estado, salud y puertos publicados.

JSON schema (--json):
  [{"service": str, "status": str, "ports": [int]}, ...]
  Empty stack: []
  Error: {"error": "<message>"} to stderr, exit 1
"""

from __future__ import annotations

import json
import sys

import typer
from rich.table import Table

from odev.commands._helpers import obtener_docker, requerir_proyecto
from odev.core.console import console
from odev.core.resolver import ProyectoAmbiguoError, ProyectoNoEncontradoError


def _parse_ports(publishers) -> list[int]:
    """Extrae puertos publicados de la lista de Publishers de docker compose ps.

    Args:
        publishers: Valor del campo Publishers/Ports del servicio.

    Returns:
        Lista de puertos publicados (enteros).
    """
    if not isinstance(publishers, list):
        return []
    ports = []
    for p in publishers:
        port = p.get("PublishedPort")
        if port:
            try:
                ports.append(int(port))
            except (ValueError, TypeError):
                pass
    return ports


def status(
    json_output: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Emite JSON a stdout para consumo por agentes.",
    ),
) -> None:
    """Muestra el estado de todos los servicios del proyecto.

    Detecta el proyecto actual, consulta docker compose ps en formato JSON,
    y presenta los resultados en una tabla formateada con Rich. Incluye
    el nombre del proyecto y el modo detectado en la cabecera.

    Con --json, emite un array JSON sin formato Rich.
    """
    from odev.main import obtener_nombre_proyecto

    if json_output:
        try:
            contexto = requerir_proyecto(obtener_nombre_proyecto())
        except (ProyectoNoEncontradoError, ProyectoAmbiguoError) as e:
            sys.stderr.write(json.dumps({"error": str(e)}) + "\n")
            raise typer.Exit(1) from e
        except typer.Exit:
            err_msg = "No se encontro un proyecto odev en el directorio actual."
            sys.stderr.write(json.dumps({"error": err_msg}) + "\n")
            raise

        dc = obtener_docker(contexto)
        servicios = dc.ps_parsed()

        resultado = []
        for svc in servicios:
            nombre = svc.get("Service", svc.get("Name", "?"))
            estado = svc.get("State", "?")
            publishers = svc.get("Publishers", svc.get("Ports", []))
            ports = _parse_ports(publishers)
            resultado.append({"service": nombre, "status": estado, "ports": ports})

        sys.stdout.write(json.dumps(resultado) + "\n")
        raise typer.Exit(0)

    contexto = requerir_proyecto(obtener_nombre_proyecto())
    dc = obtener_docker(contexto)
    servicios = dc.ps_parsed()

    nombre_proyecto = contexto.nombre
    modo = contexto.modo.value
    console.print(f"\n[bold]Proyecto:[/] {nombre_proyecto} [dim](modo: {modo})[/]\n")

    if not servicios:
        console.print("[dim]No hay servicios en ejecucion.[/]")
        return

    tabla = Table(title="Servicios")
    tabla.add_column("Servicio", style="cyan")
    tabla.add_column("Estado", style="bold")
    tabla.add_column("Salud")
    tabla.add_column("Puertos", style="dim")

    for svc in servicios:
        nombre = svc.get("Service", svc.get("Name", "?"))
        estado = svc.get("State", "?")
        salud = svc.get("Health", svc.get("Status", ""))
        puertos = svc.get("Ports", svc.get("Publishers", ""))
        if isinstance(puertos, list):
            puertos = ", ".join(
                f"{p.get('PublishedPort', '?')}:{p.get('TargetPort', '?')}"
                for p in puertos
                if p.get("PublishedPort")
            )

        estilo_estado = (
            "green" if estado == "running" else "red" if estado == "exited" else "yellow"
        )
        tabla.add_row(
            nombre,
            f"[{estilo_estado}]{estado}[/]",
            str(salud),
            str(puertos),
        )

    console.print(tabla)
