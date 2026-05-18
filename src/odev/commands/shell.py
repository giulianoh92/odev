"""Comando 'shell': abre una terminal dentro de un contenedor."""

from __future__ import annotations

from typing import Optional

import typer

from odev.commands._helpers import (
    ejecutar_passthrough,
    obtener_docker,
    requerir_proyecto,
)
from odev.core.console import error, info


def _execute_shell(contexto, service: str, command: str) -> dict:
    """Pure data-return. No I/O, no exits. MCP-callable.

    Executes a shell command in a service container and returns captured output.

    Args:
        contexto: Resolved ProjectContext.
        service: Service name (e.g. 'web', 'db').
        command: Shell command to execute (passed to bash -c).

    Returns:
        Dict with {stdout: str, stderr: str, returncode: int}.
    """
    dc = obtener_docker(contexto)
    stdout_bytes, stderr_bytes, returncode = dc.exec_capture(service, ["bash", "-c", command])
    return {
        "stdout": stdout_bytes.decode("utf-8", errors="replace"),
        "stderr": stderr_bytes.decode("utf-8", errors="replace"),
        "returncode": returncode,
    }


def _run_shell(service: str, cmd: Optional[str]) -> None:
    from odev.main import obtener_nombre_proyecto

    contexto = requerir_proyecto(obtener_nombre_proyecto())
    dc = obtener_docker(contexto)

    if cmd is None:
        info(f"Abriendo terminal en '{service}'...")
        dc.exec_cmd(service, ["bash"], interactive=True)
        return

    if not cmd.strip():
        error("El argumento -c no puede estar vacio.")
        raise typer.Exit(2)

    ejecutar_passthrough(dc, service, ["bash", "-c", cmd])


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
