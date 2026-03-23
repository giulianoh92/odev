"""Funciones auxiliares compartidas para los comandos de odev."""

from __future__ import annotations

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
        SystemExit: Si no se encuentra el proyecto o hay ambiguedad.
    """
    try:
        return resolver_proyecto(nombre_proyecto=nombre_proyecto)
    except ProyectoNoEncontradoError as e:
        error(str(e))
        raise SystemExit(1) from e
    except ProyectoAmbiguoError as e:
        warning(str(e))
        raise SystemExit(1) from e


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
