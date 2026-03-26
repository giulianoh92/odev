"""Comando ``odev reconfigure`` — regenera archivos de configuracion desde odev.yaml.

Re-lee odev.yaml y .env, luego re-renderiza docker-compose.yml y odoo.conf.
Preserva los valores de runtime del .env por defecto.
"""

from __future__ import annotations

import typer

from odev.commands._helpers import requerir_proyecto
from odev.core.console import error, info, success, warning
from odev.core.regen import RegenResult, regenerar_configuracion


def reconfigure(
    include_env: bool = typer.Option(
        False,
        "--include-env",
        help="Also regenerate .env file (WARNING: may overwrite custom ports/passwords).",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show what would be regenerated without writing files.",
    ),
) -> None:
    """Regenera docker-compose.yml y odoo.conf desde los valores actuales de odev.yaml.

    Usar despues de editar odev.yaml para propagar cambios a los archivos
    de configuracion de runtime. Por defecto, los valores del .env (puertos,
    credenciales DB) se preservan. Usar --include-env para tambien regenerar
    el archivo .env.
    """
    from odev.main import obtener_nombre_proyecto

    contexto = requerir_proyecto(obtener_nombre_proyecto())

    # Verificar que odev.yaml existe (no se puede reconfigurar sin el)
    ruta_yaml = contexto.directorio_config / ".odev.yaml"
    if not ruta_yaml.exists():
        error(
            f"No se encontro .odev.yaml en '{contexto.directorio_config}'. "
            "No se puede reconfigurar sin el archivo de configuracion. "
            "Ejecuta 'odev init' o 'odev adopt' primero."
        )
        raise typer.Exit(1)

    if dry_run:
        from odev.core.regen import necesita_regeneracion

        if necesita_regeneracion(contexto):
            info("Regeneracion necesaria: odev.yaml es mas nuevo que los archivos generados.")
        else:
            info("No se necesita regeneracion: los archivos generados estan actualizados.")
        return

    info("Regenerando configuracion desde odev.yaml...")
    resultado: RegenResult = regenerar_configuracion(
        contexto,
        include_env=include_env,
    )

    if resultado.archivos_regenerados:
        success(
            f"Se regeneraron {len(resultado.archivos_regenerados)} archivo(s). "
            "Ejecuta 'odev restart' para aplicar los cambios a los contenedores."
        )
    else:
        info("Todos los archivos ya estan actualizados.")

    for adv in resultado.advertencias:
        warning(adv)
