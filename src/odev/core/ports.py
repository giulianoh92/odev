"""Gestion de puertos para soporte multi-proyecto.

Detecta puertos disponibles y sugiere conjuntos de puertos libres
para que multiples proyectos puedan correr simultaneamente sin
conflictos.
"""

import socket

# Puertos base y sus nombres de variable de entorno
CONJUNTOS_PUERTOS: dict[str, int] = {
    "WEB_PORT": 8069,
    "PGWEB_PORT": 8081,
    "DB_PORT": 5432,
    "DEBUGPY_PORT": 5678,
    "MAILHOG_PORT": 8025,
}


def puerto_disponible(puerto: int) -> bool:
    """Verifica si un puerto TCP esta disponible para escuchar.

    Intenta hacer bind en el puerto especificado en localhost.
    Si tiene exito, el puerto esta libre.

    Args:
        puerto: Numero de puerto TCP a verificar.

    Returns:
        True si el puerto esta disponible, False si esta ocupado.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", puerto))
            return True
        except OSError:
            return False


def sugerir_puertos() -> dict[str, int]:
    """Sugiere un conjunto de puertos disponibles para un nuevo proyecto.

    Empieza con los puertos base definidos en CONJUNTOS_PUERTOS.
    Si alguno esta ocupado, incrementa TODOS los puertos del set
    en 1 hasta encontrar un set completo disponible.

    Limite de seguridad: intenta hasta 100 offsets antes de retornar
    los puertos base como fallback.

    Returns:
        Diccionario con nombre de variable -> puerto disponible.
    """
    offset = 0
    while offset < 100:  # limite de seguridad
        puertos = {nombre: base + offset for nombre, base in CONJUNTOS_PUERTOS.items()}
        if all(puerto_disponible(p) for p in puertos.values()):
            return puertos
        offset += 1
    # Fallback: retorna los puertos base sin verificar
    return CONJUNTOS_PUERTOS.copy()
