"""Deteccion de modo de operacion: legacy vs proyecto independiente.

Este modulo permite que el CLI funcione tanto en el layout viejo
(donde el repo de la herramienta ES el proyecto) como en el nuevo
(donde cada proyecto es su propio repositorio).
"""

from enum import Enum
from pathlib import Path


class ProjectMode(Enum):
    """Modo de operacion del CLI."""

    PROJECT = "project"  # Nuevo: proyecto independiente con .odev.yaml
    LEGACY = "legacy"  # Viejo: el repo de la herramienta ES el proyecto
    NONE = "none"  # No hay proyecto (fuera de cualquier directorio de proyecto)


def detect_mode(start: Path | None = None) -> tuple[ProjectMode, Path | None]:
    """Detecta el modo de operacion recorriendo el arbol de directorios hacia arriba.

    Busca indicadores en este orden de prioridad:
    1. .odev.yaml -> modo PROJECT
    2. docker-compose.yml + cli/ (carpeta del CLI viejo) -> modo LEGACY
    3. docker-compose.yml (sin cli/) -> modo PROJECT (proyecto sin .odev.yaml)
    4. Nada encontrado -> modo NONE

    Argumentos:
        start: Directorio desde donde iniciar la busqueda. Si es None, usa el
               directorio de trabajo actual.

    Retorna:
        Tupla (modo, ruta_raiz_del_proyecto o None).
    """
    current = start or Path.cwd()
    for directory in [current, *current.parents]:
        # Prioridad 1: .odev.yaml indica proyecto nuevo
        if (directory / ".odev.yaml").exists():
            return ProjectMode.PROJECT, directory

        # Prioridad 2: docker-compose.yml existe
        if (directory / "docker-compose.yml").exists():
            # Si existe cli/ como subdirectorio, es el repo legacy
            if (directory / "cli").is_dir() and (directory / "cli" / "main.py").exists():
                return ProjectMode.LEGACY, directory
            # Si no, es un proyecto (puede que creado manualmente)
            return ProjectMode.PROJECT, directory

    return ProjectMode.NONE, None
