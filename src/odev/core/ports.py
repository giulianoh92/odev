"""Gestion de puertos para soporte multi-proyecto.

Detecta puertos disponibles y asigna atomicamente conjuntos de puertos libres
para que multiples proyectos puedan correr simultaneamente sin conflictos.
allocate_ports() coordina via el registro global para evitar colisiones TOCTOU.
"""

from __future__ import annotations

import socket
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from odev.core.registry import Registry

# Puertos base y sus nombres de variable de entorno
CONJUNTOS_PUERTOS: dict[str, int] = {
    "WEB_PORT": 8069,
    "PGWEB_PORT": 8081,
    "DB_PORT": 5432,
    "DEBUGPY_PORT": 5678,
    "MAILHOG_PORT": 8025,
}

# Q10: single source of truth for all port key names
PORT_KEYS: tuple[str, ...] = tuple(CONJUNTOS_PUERTOS.keys())


class PortAllocationError(RuntimeError):
    """Se lanza cuando no se pueden encontrar puertos libres tras el budget de offsets."""


def puerto_disponible(puerto: int) -> bool:
    """Verifica si un puerto TCP esta disponible para escuchar.

    Intenta hacer bind en el puerto especificado en localhost.
    Si tiene exito, el puerto esta libre.

    Argumentos:
        puerto: Numero de puerto TCP a verificar.

    Retorna:
        True si el puerto esta disponible, False si esta ocupado.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", puerto))
            return True
        except OSError:
            return False


def allocate_ports(project_name: str, registry: Registry) -> dict[str, int]:
    """Reclama atomicamente un conjunto de puertos libres para un proyecto.

    Algoritmo (claim-then-render, lock < 50ms):
      Bajo el threading.Lock del registro:
        Para offset en 0..99:
          - Genera candidatos: {var: base+offset for ...}
          - Si algun candidato esta reclamado en el registro: skip
          - Si algun socket no esta libre: skip
          - Reclama en registro via asignar_puertos() (atomico con flock)
          - Retorna
      Si se agotan 100 offsets: lanza PortAllocationError

    El lock se sostiene SOLO durante esta funcion (< 50ms).
    El wizard continua sin lock despues de que esta funcion retorna.

    Argumentos:
        project_name: Nombre del proyecto que reclama los puertos.
        registry: Instancia de Registry a usar para coordinacion.

    Retorna:
        Diccionario {nombre_variable: numero_puerto} con el set reclamado.

    Lanza:
        PortAllocationError: Si no se encontraron puertos tras 100 offsets.
    """
    from odev.core.registry import _REGISTRY_THREAD_LOCK

    with _REGISTRY_THREAD_LOCK:
        # Bajo el lock: leer estado actual y encontrar offset libre
        ocupados = registry.puertos_ocupados()

        for offset in range(100):
            candidatos = {var: base + offset for var, base in CONJUNTOS_PUERTOS.items()}

            # Saltar si algun candidato esta reclamado en el registro
            if any(p in ocupados for p in candidatos.values()):
                continue

            # Saltar si algun socket no esta libre
            if not all(puerto_disponible(p) for p in candidatos.values()):
                continue

            # Reclamar en el registro. El thread lock ya es exclusivo, pero
            # _escribir tambien adquiere fcntl para coordinacion multi-proceso.
            # Para evitar deadlock, llamamos _escribir directamente (que reacquire
            # el thread lock) debemos llamar a asignar_puertos que usa _escribir.
            # Dado que _escribir intentaria re-adquirir _REGISTRY_THREAD_LOCK,
            # usamos _escribir_sin_thread_lock que solo hace fcntl.
            registry._asignar_puertos_bajo_lock(project_name, candidatos)
            return candidatos

    raise PortAllocationError(
        "No hay puertos libres tras 100 offsets. "
        "Ejecuta 'odev doctor' para liberar entradas huerfanas."
    )


