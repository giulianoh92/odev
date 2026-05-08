"""Comando 'shell': abre una terminal dentro de un contenedor."""

from __future__ import annotations

import subprocess
import sys
from typing import Optional

import typer

from odev.commands._helpers import obtener_docker, requerir_proyecto
from odev.core.console import error, info


def _run_shell(service: str, cmd: Optional[str]) -> None:
    """Implementacion principal — testeable sin Typer runner.

    Argumentos:
        service: Nombre del servicio donde ejecutar el comando.
        cmd:     Comando a ejecutar de forma no-interactiva, o None para modo interactivo.
    """
    from odev.main import obtener_nombre_proyecto

    contexto = requerir_proyecto(obtener_nombre_proyecto())
    dc = obtener_docker(contexto)

    if cmd is None:
        # Ruta interactiva — comportamiento identico al original
        info(f"Abriendo terminal en '{service}'...")
        dc.exec_cmd(service, ["bash"], interactive=True)
        return

    # Ruta no-interactiva: validar, exec, passthrough, propagar exit
    if not cmd.strip():
        error("El argumento -c no puede estar vacio.")
        raise typer.Exit(2)

    try:
        result = dc.exec_cmd(service, ["bash", "-c", cmd], interactive=False)
    except subprocess.CalledProcessError as e:
        sys.stderr.buffer.write(e.stderr or b"")
        raise typer.Exit(e.returncode) from e

    sys.stdout.buffer.write(result.stdout or b"")
    sys.stderr.buffer.write(result.stderr or b"")
    raise typer.Exit(result.returncode)


def shell(
    service: str = typer.Argument(
        "web",
        help="Servicio donde abrir la terminal (web, db).",
    ),
    cmd: Optional[str] = typer.Option(
        None,
        "-c",
        "--cmd",
        help="Ejecuta un comando bash de forma no-interactiva y termina.",
    ),
) -> None:
    """Abre una terminal bash dentro de un contenedor del stack."""
    _run_shell(service, cmd)
