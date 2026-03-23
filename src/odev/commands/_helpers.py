"""Funciones auxiliares compartidas para los comandos de odev."""

from __future__ import annotations

import typer

from odev.core.console import error, warning
from odev.core.docker import DockerCompose
from odev.core.paths import ProjectPaths
from odev.core.resolver import (
    ProjectContext,
    ProyectoAmbiguoError,
    ProyectoNoEncontradoError,
    resolver_proyecto,
)


def requerir_proyecto(nombre_proyecto: str | None = None) -> ProjectContext:
    """Resuelve el proyecto actual o lanza error con mensaje amigable.

    Usado por todos los comandos que necesitan estar en un proyecto.
    Maneja los errores del resolver y muestra mensajes utiles al usuario.

    Args:
        nombre_proyecto: Nombre explicito del proyecto (por ej. de --project).

    Returns:
        ProjectContext con la informacion del proyecto resuelto.

    Raises:
        typer.Exit: Si no se encuentra el proyecto o hay ambiguedad.
    """
    try:
        return resolver_proyecto(nombre_proyecto=nombre_proyecto)
    except ProyectoNoEncontradoError as e:
        error(str(e))
        raise typer.Exit(1) from e
    except ProyectoAmbiguoError as e:
        warning(str(e))
        raise typer.Exit(1) from e


def obtener_docker(contexto: ProjectContext) -> DockerCompose:
    """Crea una instancia de DockerCompose desde el contexto del proyecto.

    Args:
        contexto: Contexto del proyecto resuelto.

    Returns:
        Instancia de DockerCompose configurada segun el contexto.
    """
    return DockerCompose.from_context(contexto)


def obtener_rutas(contexto: ProjectContext) -> ProjectPaths:
    """Crea una instancia de ProjectPaths desde el contexto del proyecto.

    Args:
        contexto: Contexto del proyecto resuelto.

    Returns:
        Instancia de ProjectPaths configurada segun el contexto.
    """
    return ProjectPaths(
        project_root=contexto.directorio_config,
        addon_paths=contexto.config.rutas_addons if contexto.config else None,
    )


def ejecutar_operacion_modulo(
    modulo: str,
    flag_odoo: str,
    verbo_gerundio: str,
    verbo_pasado: str,
) -> None:
    """Ejecuta una operacion de modulo Odoo (instalar o actualizar).

    Argumentos:
        modulo: Nombre tecnico del modulo.
        flag_odoo: Flag de Odoo ('-i' para instalar, '-u' para actualizar).
        verbo_gerundio: Verbo en gerundio para mensajes (ej. 'Instalando').
        verbo_pasado: Verbo en pasado para mensajes (ej. 'instalado').
    """
    from odev.main import obtener_nombre_proyecto
    from odev.core.config import load_env
    from odev.core.console import info, success

    contexto = requerir_proyecto(obtener_nombre_proyecto())
    rutas = obtener_rutas(contexto)

    valores_env = load_env(rutas.env_file)
    nombre_bd = valores_env.get("DB_NAME", "odoo_db")

    dc = obtener_docker(contexto)

    info(f"{verbo_gerundio} modulo: {modulo}")
    dc.exec_cmd(
        "web",
        ["odoo", flag_odoo, modulo, "-d", nombre_bd, "--stop-after-init"],
        interactive=True,
    )

    info("Reiniciando servicio web...")
    dc.restart("web")
    success(f"Modulo '{modulo}' {verbo_pasado} y servicio web reiniciado.")
