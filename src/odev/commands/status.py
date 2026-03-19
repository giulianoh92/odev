"""Comando 'status': muestra el estado de los servicios del proyecto.

Presenta una tabla con informacion de cada servicio de Docker Compose
incluyendo nombre, estado, salud y puertos publicados.
"""

import typer
from rich.table import Table

from odev.core.console import console, error
from odev.core.docker import DockerCompose
from odev.core.paths import ProjectPaths


def status() -> None:
    """Muestra el estado de todos los servicios del proyecto.

    Detecta el proyecto actual, consulta docker compose ps en formato JSON,
    y presenta los resultados en una tabla formateada con Rich. Incluye
    el nombre del proyecto y el modo detectado en la cabecera.
    """
    try:
        rutas = ProjectPaths()
    except FileNotFoundError:
        error("No se encontro un proyecto odev. Ejecuta 'odev init' para crear uno.")
        raise typer.Exit(1)

    dc = DockerCompose(rutas.root)
    servicios = dc.ps_parsed()

    nombre_proyecto = rutas.root.name
    modo = rutas.mode.value
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
            "green" if estado == "running"
            else "red" if estado == "exited"
            else "yellow"
        )
        tabla.add_row(
            nombre,
            f"[{estilo_estado}]{estado}[/]",
            str(salud),
            str(puertos),
        )

    console.print(tabla)
