"""Verificacion pre-vuelo de puertos antes de docker compose up.

Clasifica cada puerto del proyecto como libre, propio (contenedor del
mismo proyecto ya corriendo) o foraneo (otro proceso u otro proyecto).
Implementa REQ-UP-1 y REQ-UP-2.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from odev.core.ports import puerto_disponible

if TYPE_CHECKING:
    from odev.core.docker import DockerCompose
    from odev.core.registry import Registry
    from odev.core.resolver import ProjectContext


@dataclass
class PortStatus:
    """Estado de un puerto individual en la verificacion pre-vuelo.

    Atributos:
        nombre: Nombre de la variable de entorno (ej. "WEB_PORT").
        puerto: Numero de puerto TCP.
        estado: Clasificacion del puerto:
            - "free": disponible para bind.
            - "own_running": ocupado por un contenedor del proyecto actual.
            - "foreign_known": ocupado por otro proyecto conocido en el registro.
            - "foreign_unknown": ocupado por proceso sin entrada en el registro.
        propietario: Nombre del proyecto propietario si se conoce, None si no.
    """

    nombre: str
    puerto: int
    estado: str
    propietario: str | None = None


@dataclass
class PreflightResult:
    """Resultado agregado de la verificacion de todos los puertos del proyecto.

    Atributos:
        statuses: Lista de PortStatus, uno por puerto verificado.
    """

    statuses: list[PortStatus] = field(default_factory=list)

    @property
    def has_fail(self) -> bool:
        """True si hay al menos un puerto foraneo (que impide el arranque)."""
        return any(s.estado in ("foreign_known", "foreign_unknown") for s in self.statuses)

    @property
    def warnings(self) -> list[PortStatus]:
        """Lista de puertos con estado own_running (WARN, no bloquea)."""
        return [s for s in self.statuses if s.estado == "own_running"]

    @property
    def fails(self) -> list[PortStatus]:
        """Lista de puertos con estado foreign_known o foreign_unknown (FAIL)."""
        return [s for s in self.statuses if s.estado in ("foreign_known", "foreign_unknown")]


def _container_binds_port(container: dict, puerto: int, project_name: str) -> bool:
    """Verifica si un contenedor del proyecto actual publica el puerto dado.

    Argumentos:
        container: Diccionario de docker compose ps_parsed para un servicio.
        puerto: Numero de puerto a verificar.
        project_name: Nombre del proyecto compose actual.

    Retorna:
        True si el contenedor pertenece al proyecto y publica el puerto.
    """
    labels = container.get("Labels") or {}
    if isinstance(labels, dict):
        compose_project = labels.get("com.docker.compose.project", "")
    else:
        compose_project = ""

    if compose_project != project_name:
        return False

    publishers = container.get("Publishers") or []
    for pub in publishers:
        if isinstance(pub, dict) and pub.get("PublishedPort") == puerto:
            return True
    return False


def _find_owner_in_registry(registry: Registry, puerto: int) -> str | None:
    """Busca en el registro que proyecto tiene reclamado el puerto dado.

    Argumentos:
        registry: Instancia de Registry donde buscar.
        puerto: Numero de puerto a buscar.

    Retorna:
        Nombre del proyecto propietario, o None si no se encuentra.
    """
    entries = registry._leer()
    for nombre, entry in entries.items():
        if entry.ports and puerto in entry.ports.values():
            return nombre
    return None


def classify_bound_port(
    puerto: int,
    project_name: str,
    dc: DockerCompose,
    registry: Registry,
) -> tuple[str, str | None]:
    """Clasifica un puerto que esta ocupado (no disponible para bind).

    Argumentos:
        puerto: Numero de puerto TCP ocupado.
        project_name: Nombre del proyecto que quiere usar el puerto.
        dc: Instancia de DockerCompose para consultar contenedores activos.
        registry: Registro global para buscar propietario.

    Retorna:
        Tupla (estado, propietario):
            - ("own_running", project_name) si pertenece al proyecto actual.
            - ("foreign_known", owner) si pertenece a otro proyecto registrado.
            - ("foreign_unknown", None) si no se puede identificar el propietario.
    """
    contenedores = dc.ps_parsed()

    # Verificar si el puerto lo tiene un contenedor del proyecto actual
    for contenedor in contenedores:
        if _container_binds_port(contenedor, puerto, project_name):
            return "own_running", project_name

    # Buscar en el registro
    owner = _find_owner_in_registry(registry, puerto)
    if owner and owner != project_name:
        return "foreign_known", owner

    return "foreign_unknown", None


def verificar_puertos_pre_up(
    contexto: ProjectContext,
    dc: DockerCompose,
    registry: Registry,
    puertos: dict[str, int],
) -> PreflightResult:
    """Verifica los puertos del proyecto antes de invocar docker compose up.

    Para cada puerto en el diccionario dado, clasifica su estado:
    - libre (free): sin bind, todo ok.
    - propio corriendo (own_running): contenedor del mismo proyecto activo.
    - foraneo conocido (foreign_known): otro proyecto del registro.
    - foraneo desconocido (foreign_unknown): proceso sin entrada en registro.

    Argumentos:
        contexto: Contexto del proyecto resuelto (nombre, rutas).
        dc: Instancia de DockerCompose del proyecto.
        registry: Registro global de proyectos.
        puertos: Diccionario {nombre_variable: numero_puerto} del .env.

    Retorna:
        PreflightResult con el estado de cada puerto.
    """
    statuses: list[PortStatus] = []

    for nombre, numero_puerto in puertos.items():
        if puerto_disponible(numero_puerto):
            statuses.append(
                PortStatus(
                    nombre=nombre,
                    puerto=numero_puerto,
                    estado="free",
                    propietario=None,
                )
            )
            continue

        # Puerto ocupado — clasificar
        estado, propietario = classify_bound_port(
            numero_puerto,
            contexto.nombre,
            dc,
            registry,
        )
        statuses.append(
            PortStatus(
                nombre=nombre,
                puerto=numero_puerto,
                estado=estado,
                propietario=propietario,
            )
        )

    return PreflightResult(statuses=statuses)
