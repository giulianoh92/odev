"""Resolucion unificada de proyectos odev.

Provee una funcion central ``resolver_proyecto`` que determina el
contexto del proyecto actual combinando multiples estrategias:
busqueda inline (.odev.yaml), consulta al registro global y
deteccion de proyectos legacy (odoo-dev-env viejo).

Todos los comandos del CLI deben usar este modulo para obtener
el ``ProjectContext`` sobre el que van a operar.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from odev.core.project import ProjectConfig
from odev.core.registry import Registry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums y dataclasses
# ---------------------------------------------------------------------------


class ModoProyecto(str, Enum):
    """Modo de operacion de un proyecto odev."""

    INLINE = "inline"       # Config vive dentro del directorio del proyecto
    EXTERNAL = "external"   # Config vive en ~/.odev/projects/<nombre>/
    LEGACY = "legacy"       # Formato viejo odoo-dev-env (compatibilidad hacia atras)


@dataclass
class ProjectContext:
    """Contexto completo de un proyecto resuelto.

    Atributos:
        nombre: Nombre del proyecto.
        modo: Modo de operacion (inline, external o legacy).
        directorio_config: Directorio donde viven .odev.yaml / docker-compose.
        directorio_trabajo: Directorio donde vive el codigo / addons.
        config: Configuracion cargada desde .odev.yaml, o None si no aplica.
    """

    nombre: str
    modo: ModoProyecto
    directorio_config: Path
    directorio_trabajo: Path
    config: ProjectConfig | None


# ---------------------------------------------------------------------------
# Excepciones
# ---------------------------------------------------------------------------


class ProyectoNoEncontradoError(Exception):
    """No se encontro un proyecto odev en el directorio actual."""

    def __init__(self, directorio: Path) -> None:
        self.directorio = directorio
        super().__init__(
            f"No se encontró un proyecto odev en '{directorio}' ni en el registro."
        )


class ProyectoAmbiguoError(Exception):
    """Multiples proyectos coinciden con el directorio actual."""

    def __init__(self, directorio: Path, proyectos: list[str]) -> None:
        self.directorio = directorio
        self.proyectos = proyectos
        super().__init__(
            f"Múltiples proyectos coinciden con '{directorio}': "
            f"{', '.join(proyectos)}. "
            f"Usá --project <nombre> para especificar."
        )


# ---------------------------------------------------------------------------
# Funciones de busqueda internas
# ---------------------------------------------------------------------------


def _modo_desde_string(valor: str) -> ModoProyecto:
    """Convierte un string del registro a ModoProyecto.

    Argumentos:
        valor: Valor almacenado en el registro (ej. "inline", "external").

    Retorna:
        El ModoProyecto correspondiente, o EXTERNAL como valor por defecto.
    """
    try:
        return ModoProyecto(valor)
    except ValueError:
        logger.warning(
            "Modo desconocido '%s' en el registro, usando EXTERNAL.", valor
        )
        return ModoProyecto.EXTERNAL


def _buscar_inline(cwd: Path) -> ProjectContext | None:
    """Busca .odev.yaml subiendo por el arbol de directorios.

    Recorre desde *cwd* hacia la raiz buscando un archivo ``.odev.yaml``.
    Si lo encuentra, carga la configuracion y retorna un contexto INLINE.

    Argumentos:
        cwd: Directorio de inicio para la busqueda ascendente.

    Retorna:
        ProjectContext en modo INLINE si se encuentra, None si no.
    """
    actual = cwd.resolve()
    while True:
        odev_yaml = actual / ".odev.yaml"
        if odev_yaml.is_file():
            config = ProjectConfig(actual)
            nombre = config.nombre_proyecto or actual.name
            return ProjectContext(
                nombre=nombre,
                modo=ModoProyecto.INLINE,
                directorio_config=actual,
                directorio_trabajo=actual,
                config=config,
            )
        padre = actual.parent
        if padre == actual:
            break
        actual = padre
    return None


def _buscar_external(cwd: Path) -> ProjectContext | None | list[ProjectContext]:
    """Busca en el registro global por directorio de trabajo.

    Consulta ``Registry.buscar_por_directorio`` para encontrar proyectos
    registrados cuyo directorio de trabajo contenga *cwd*.

    Argumentos:
        cwd: Directorio actual a consultar contra el registro.

    Retorna:
        - None si no hay coincidencias.
        - Un ProjectContext en modo EXTERNAL si hay exactamente una.
        - Una lista de ProjectContext si hay multiples (ambiguedad).
    """
    registro = Registry()
    coincidencias = registro.buscar_por_directorio(cwd)

    if len(coincidencias) == 0:
        return None

    if len(coincidencias) == 1:
        entry = coincidencias[0]
        config = _cargar_config_seguro(entry.directorio_config)
        return ProjectContext(
            nombre=entry.nombre,
            modo=ModoProyecto.EXTERNAL,
            directorio_config=entry.directorio_config,
            directorio_trabajo=entry.directorio_trabajo,
            config=config,
        )

    # Multiples coincidencias — retornar lista para que el llamador maneje
    contextos: list[ProjectContext] = []
    for entry in coincidencias:
        config = _cargar_config_seguro(entry.directorio_config)
        contextos.append(
            ProjectContext(
                nombre=entry.nombre,
                modo=ModoProyecto.EXTERNAL,
                directorio_config=entry.directorio_config,
                directorio_trabajo=entry.directorio_trabajo,
                config=config,
            )
        )
    return contextos


def _buscar_legacy(cwd: Path) -> ProjectContext | None:
    """Detecta proyectos legacy (formato odoo-dev-env viejo).

    Busca subiendo por el arbol de directorios un directorio que tenga
    ``docker-compose.yml`` y un subdirectorio ``cli/``, que es la
    firma del tooling viejo.

    Argumentos:
        cwd: Directorio de inicio para la busqueda ascendente.

    Retorna:
        ProjectContext en modo LEGACY si se detecta, None si no.
    """
    actual = cwd.resolve()
    while True:
        tiene_compose = (actual / "docker-compose.yml").is_file()
        tiene_cli = (actual / "cli").is_dir()
        if tiene_compose and tiene_cli:
            return ProjectContext(
                nombre=actual.name,
                modo=ModoProyecto.LEGACY,
                directorio_config=actual,
                directorio_trabajo=actual,
                config=None,
            )
        padre = actual.parent
        if padre == actual:
            break
        actual = padre
    return None


def _cargar_config_seguro(directorio_config: Path) -> ProjectConfig | None:
    """Intenta cargar ProjectConfig sin fallar si no existe .odev.yaml.

    Argumentos:
        directorio_config: Directorio donde buscar .odev.yaml.

    Retorna:
        ProjectConfig cargada, o None si el archivo no existe.
    """
    try:
        return ProjectConfig(directorio_config)
    except FileNotFoundError:
        logger.debug(
            "No se encontro .odev.yaml en %s, config sera None.",
            directorio_config,
        )
        return None


# ---------------------------------------------------------------------------
# Funcion principal de resolucion
# ---------------------------------------------------------------------------


def resolver_proyecto(
    cwd: Path | None = None,
    nombre_proyecto: str | None = None,
) -> ProjectContext:
    """Resuelve el contexto del proyecto actual.

    Esta es la funcion central que todos los comandos del CLI usan para
    determinar sobre que proyecto estan operando. Aplica las siguientes
    estrategias en orden de prioridad:

    1. **Nombre explicito** — si se pasa *nombre_proyecto*, se busca en
       el registro global. Si no existe, lanza ``ProyectoNoEncontradoError``.
    2. **INLINE busqueda ascendente** — desde *cwd*, sube por el arbol de directorios
       buscando ``.odev.yaml``.
    3. **EXTERNAL registro** — consulta el registro global por directorio
       de trabajo. Si hay multiples coincidencias, lanza ``ProyectoAmbiguoError``.
    4. **LEGACY** — detecta el patron viejo (docker-compose.yml + cli/).
    5. **No encontrado** — lanza ``ProyectoNoEncontradoError``.

    Argumentos:
        cwd: Directorio de trabajo actual. Si es None, usa ``Path.cwd()``.
        nombre_proyecto: Nombre explicito del proyecto (por ej. de ``--project``).

    Retorna:
        ProjectContext con toda la informacion del proyecto resuelto.

    Lanza:
        ProyectoNoEncontradoError: Si no se puede resolver ningun proyecto.
        ProyectoAmbiguoError: Si multiples proyectos coinciden y no se
            especifico un nombre explicito.
    """
    directorio = (cwd or Path.cwd()).resolve()

    # --- Estrategia 1: nombre explicito via registro ---
    if nombre_proyecto is not None:
        registro = Registry()
        entry = registro.obtener(nombre_proyecto)
        if entry is None:
            raise ProyectoNoEncontradoError(directorio)
        config = _cargar_config_seguro(entry.directorio_config)
        return ProjectContext(
            nombre=entry.nombre,
            modo=_modo_desde_string(entry.modo),
            directorio_config=entry.directorio_config,
            directorio_trabajo=entry.directorio_trabajo,
            config=config,
        )

    # --- Estrategia 2: busqueda INLINE (.odev.yaml ascendente) ---
    contexto_inline = _buscar_inline(directorio)
    if contexto_inline is not None:
        return contexto_inline

    # --- Estrategia 3: busqueda EXTERNAL (registro por directorio) ---
    resultado_external = _buscar_external(directorio)
    if resultado_external is not None:
        if isinstance(resultado_external, list):
            nombres = [ctx.nombre for ctx in resultado_external]
            raise ProyectoAmbiguoError(directorio, nombres)
        return resultado_external

    # --- Estrategia 4: deteccion LEGACY ---
    contexto_legacy = _buscar_legacy(directorio)
    if contexto_legacy is not None:
        return contexto_legacy

    # --- Estrategia 5: no encontrado ---
    raise ProyectoNoEncontradoError(directorio)
