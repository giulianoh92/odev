"""Comando 'addon-install': instala uno o varios modulos Odoo por primera vez."""

import typer

from odev.commands._helpers import (
    ejecutar_odoo_compacto,
    obtener_docker,
    obtener_rutas,
    parsear_modulos_csv,
    requerir_proyecto,
    validar_modulos,
)
from odev.core.config import load_env


def install(
    module: str = typer.Argument(
        ...,
        help=("Modulo(s) a instalar. CSV soportado: 'm1,m2,m3'. 'all' solo como token unico."),
    ),
    no_validate: bool = typer.Option(
        False,
        "--no-validate",
        help="Omite la validacion previa contra addons-path.",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Muestra el log crudo completo de Odoo en vivo (comportamiento pre-0.7.0).",
    ),
) -> None:
    """Instala modulo(s) Odoo por primera vez y reinicia el servicio web.

    Por default captura el log de Odoo y muestra solo lo relevante
    (WARNING/ERROR/CRITICAL, tracebacks, linea de exito y resumen).
    Usa --verbose/-v para ver el log crudo completo en vivo.
    """
    from odev.main import obtener_nombre_proyecto

    contexto = requerir_proyecto(obtener_nombre_proyecto())
    modulos = parsear_modulos_csv(module)
    validar_modulos(modulos, contexto, no_validate=no_validate)

    rutas = obtener_rutas(contexto)
    valores_env = load_env(rutas.env_file)
    nombre_bd = valores_env.get("DB_NAME", "odoo_db")

    dc = obtener_docker(contexto)

    from odev.core.console import error, info, success

    modulos_csv = ",".join(modulos)
    comando = ["odoo", "-i", modulos_csv, "-d", nombre_bd, "--stop-after-init"]
    info(f"Instalando modulo(s): {modulos_csv}")

    if verbose:
        # Ruta pre-0.7.0: log crudo interactivo, sin filtro ni exit code derivado
        dc.exec_cmd("web", comando, interactive=True)
        codigo_final = 0
    else:
        codigo_final = ejecutar_odoo_compacto(dc, "web", comando, cantidad_modulos=len(modulos))

    info("Reiniciando servicio web...")
    dc.restart("web")

    if codigo_final != 0:
        error(f"Instalacion de '{modulos_csv}' termino con errores (exit {codigo_final}).")
        raise typer.Exit(codigo_final)
    success(f"Modulo(s) '{modulos_csv}' instalado(s) y servicio web reiniciado.")
