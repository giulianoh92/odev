"""Comando 'self-update': actualiza odev a la ultima version disponible.

Ejecuta pip install --upgrade odev y reporta el resultado al usuario.
Muestra la version actual antes de intentar la actualizacion y
distingue entre: actualizacion exitosa, ya esta al dia, o error.
"""

import subprocess
import sys

import typer

from odev import __version__
from odev.core.console import error, info, success


def self_update() -> None:
    """Actualiza odev a la ultima version disponible.

    Ejecuta 'pip install --upgrade odev' usando el mismo interprete
    de Python que esta ejecutando el CLI, para asegurar que se
    actualiza la instalacion correcta.
    """
    info(f"Version actual: {__version__}")
    info("Buscando actualizaciones...")

    # Usar sys.executable para garantizar que se usa el pip correcto
    ejecutable_pip = [sys.executable, "-m", "pip"]

    try:
        resultado = subprocess.run(
            [*ejecutable_pip, "install", "--upgrade", "odev"],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        error("La operacion excedio el tiempo limite (120s). Intenta manualmente:")
        info("  pip install --upgrade odev")
        raise typer.Exit(1)
    except FileNotFoundError:
        error("No se encontro pip. Intenta manualmente:")
        info("  pip install --upgrade odev")
        raise typer.Exit(1)

    salida_completa = resultado.stdout + resultado.stderr

    if resultado.returncode != 0:
        error("Error al actualizar. Salida del comando:")
        info(salida_completa.strip())
        info("Intenta manualmente: pip install --upgrade odev")
        raise typer.Exit(1)

    # Determinar si realmente se actualizo o ya estaba al dia
    salida_lower = salida_completa.lower()
    if "successfully installed" in salida_lower:
        success("odev actualizado exitosamente.")
        info("Reinicia tu terminal o ejecuta 'odev --version' para verificar.")
    elif "already satisfied" in salida_lower or "already up-to-date" in salida_lower:
        info("Ya tienes la ultima version disponible.")
    else:
        # Caso ambiguo: pip termino con exito pero no podemos determinar que paso
        info("Proceso completado. Verifica con 'odev --version'.")
