"""Comando 'test': ejecuta tests de modulos Odoo.

Ejecuta los tests de un modulo especifico o de todos los modulos
usando el framework de tests nativo de Odoo.
"""

from typing import Optional

import typer

from odev.commands._helpers import obtener_docker, obtener_rutas, requerir_proyecto
from odev.core.config import load_env
from odev.core.console import info


def test(
    module: str = typer.Argument(
        ...,
        help="Nombre del modulo a testear, o 'all' para ejecutar todos los tests.",
    ),
    log_level: Optional[str] = typer.Option(
        "test",
        "--log-level",
        "-l",
        help="Nivel de log (test, debug, info, warn, error).",
    ),
) -> None:
    """Ejecuta los tests de un modulo Odoo.

    Ejecuta los tests del modulo especificado usando el framework
    de tests de Odoo. Usa 'all' para ejecutar todos los tests
    disponibles (puede tomar bastante tiempo).
    """
    from odev.main import obtener_nombre_proyecto
    contexto = requerir_proyecto(obtener_nombre_proyecto())
    rutas = obtener_rutas(contexto)

    valores_env = load_env(rutas.env_file)
    nombre_bd = valores_env.get("DB_NAME", "odoo_db")

    comando = [
        "odoo",
        "--test-enable",
        "--stop-after-init",
        "-d", nombre_bd,
        "--http-port=8070",
        f"--log-level={log_level}",
    ]

    if module != "all":
        comando.extend(["-u", module, "--test-tags", f"/{module}"])
        info(f"Ejecutando tests del modulo: {module}")
    else:
        info("Ejecutando todos los tests (esto puede tomar un rato)...")

    dc = obtener_docker(contexto)
    dc.exec_cmd("web", comando, interactive=True)
