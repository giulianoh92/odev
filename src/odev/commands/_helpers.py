"""Funciones auxiliares compartidas para los comandos de odev."""

from __future__ import annotations

import subprocess
import sys
from typing import NoReturn

import typer

from odev.core.console import error, warning
from odev.core.detect import detectar_layout
from odev.core.docker import DockerCompose
from odev.core.paths import ProjectPaths
from odev.core.resolver import (
    ProjectContext,
    ProyectoAmbiguoError,
    ProyectoNoEncontradoError,
    resolver_proyecto,
)

# ---------------------------------------------------------------------------
# Modulos builtin de Odoo — bypass del pre-flight de validacion
# ---------------------------------------------------------------------------

MODULOS_BUILTIN: frozenset[str] = frozenset({
    "base", "web", "web_tour", "mail", "bus", "barcodes",
    "sale", "sale_management", "purchase", "account",
    "stock", "hr", "hr_holidays", "point_of_sale",
    "calendar", "contacts", "fleet", "lunch", "note",
    "portal", "product", "uom", "resource", "rating",
    "auth_signup", "digest",
})


def parsear_modulos_csv(valor: str) -> list[str]:
    """Parsea CSV de modulos en una lista normalizada.

    Comportamiento:
      - Split por coma, strip whitespace, descarta vacios.
      - Dedup preservando el orden de primera aparicion.
      - 'all' permitido SOLO como token unico — mezclado con otros
        levanta typer.Exit(2).
      - CSV de un solo elemento ('mod1') retorna ['mod1'] — backward-compat.

    Argumentos:
        valor: cadena tal cual la entrega Typer (un solo token shell).

    Retorna:
        Lista de nombres de modulo normalizados.

    Raises:
        typer.Exit(2): si la lista es vacia o 'all' aparece con otros tokens.
    """
    partes = [p.strip() for p in valor.split(",")]
    partes = [p for p in partes if p]

    if not partes:
        sys.stderr.write("Lista de modulos vacia\n")
        raise typer.Exit(2)

    seen: set[str] = set()
    result: list[str] = []
    for p in partes:
        if p not in seen:
            seen.add(p)
            result.append(p)

    if "all" in result and len(result) > 1:
        sys.stderr.write("'all' no puede combinarse con otros modulos\n")
        raise typer.Exit(2)

    return result


def listar_modulos_disponibles(contexto: ProjectContext) -> set[str]:
    """Enumera modulos descubribles via detectar_layout.

    Reutiliza la logica de deteccion existente. Set para lookup O(1).
    Retorna set vacio si layout es desconocido (modulos_encontrados == 0)
    para que callers traten el caso como 'fallback: no bloquear'.

    Argumentos:
        contexto: contexto del proyecto resuelto.

    Retorna:
        Conjunto de nombres tecnicos de modulos detectados en addons-path.
    """
    layout = detectar_layout(contexto.directorio_config)
    if layout.modulos_encontrados == 0:
        return set()
    nombres: set[str] = set()
    for ruta_addons in layout.rutas_addons:
        for p in sorted(ruta_addons.iterdir()):
            if (p / "__manifest__.py").exists():
                nombres.add(p.name)
    return nombres


def validar_modulos(
    nombres: list[str],
    contexto: ProjectContext,
    no_validate: bool = False,
) -> None:
    """Valida una lista de modulos contra addons-path.

    Reglas:
      - 'all' como unico token: bypass total.
      - no_validate=True: bypass total (parsing ya corrio).
      - Cada nombre se valida; los builtins en MODULOS_BUILTIN se aceptan.
      - Si layout es desconocido (set vacio), no bloquea (fallback existente).
      - En error: raise typer.Exit(2) con la lista COMPLETA de faltantes.

    Argumentos:
        nombres: lista normalizada (post parsear_modulos_csv).
        contexto: contexto del proyecto.
        no_validate: si True, omite validacion contra disco.

    Raises:
        typer.Exit(2): si uno o mas modulos no existen y no son builtin.
    """
    if nombres == ["all"]:
        return
    if no_validate:
        return

    # Filtrar builtins antes de ir al disco — si todos son builtins, no hay nada
    # que validar en filesystem
    a_validar = [n for n in nombres if n not in MODULOS_BUILTIN]
    if not a_validar:
        return

    disponibles = listar_modulos_disponibles(contexto)
    if not disponibles:
        return  # Layout desconocido — fallback existente

    faltantes = [n for n in a_validar if n not in disponibles]
    if faltantes:
        sys.stderr.write(f"Modulos no encontrados: {', '.join(faltantes)}\n")
        raise typer.Exit(2)


def requerir_proyecto(nombre_proyecto: str | None = None) -> ProjectContext:
    """Resuelve el proyecto actual o lanza error con mensaje amigable.

    Usado por todos los comandos que necesitan estar en un proyecto.
    Maneja los errores del resolver y muestra mensajes utiles al usuario.

    Args:
        nombre_proyecto: Nombre explicito del proyecto (por ej. de --project).

    Returns:
        ProjectContext con la informacion del proyecto resuelto.

    Raises:
        typer.Exit: Si no se encuentra el proyecto o hay ambiguedad.
    """
    try:
        return resolver_proyecto(nombre_proyecto=nombre_proyecto)
    except ProyectoNoEncontradoError as e:
        error(str(e))
        raise typer.Exit(1) from e
    except ProyectoAmbiguoError as e:
        warning(str(e))
        raise typer.Exit(1) from e


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


def ejecutar_passthrough(
    dc: DockerCompose,
    service: str,
    args: list[str],
    *,
    stdin_data: bytes | None = None,
) -> NoReturn:
    """Ejecuta un comando no-interactivo en el contenedor y propaga IO + exit.

    Wrapper de `dc.exec_cmd(interactive=False)` para los comandos
    agent-friendly (`shell -c`, `sql`, `py`). En CalledProcessError escribe
    `e.stderr` en stderr y termina con `e.returncode`. En exito escribe
    stdout/stderr crudos y termina con el returncode del subproceso.
    Siempre termina con `typer.Exit`.

    Argumentos:
        dc:         Instancia DockerCompose ya resuelta.
        service:    Servicio destino (ej: 'web', 'db').
        args:       Argv del comando dentro del contenedor.
        stdin_data: Datos opcionales para stdin (None = sin pipe).
    """
    kwargs: dict = {"interactive": False}
    if stdin_data is not None:
        kwargs["stdin_data"] = stdin_data
    try:
        result = dc.exec_cmd(service, args, **kwargs)
    except subprocess.CalledProcessError as e:
        sys.stderr.buffer.write(e.stderr or b"")
        raise typer.Exit(e.returncode) from e
    sys.stdout.buffer.write(result.stdout or b"")
    sys.stderr.buffer.write(result.stderr or b"")
    raise typer.Exit(result.returncode)


def validar_modulo_existe(nombre: str, contexto: ProjectContext) -> None:
    """Wrapper retro-compatible; delega en validar_modulos.

    Mantiene la misma semantica publica y superficie de mock que antes.
    El mock path 'odev.commands._helpers.detectar_layout' sigue siendo valido
    porque validar_modulos llama a listar_modulos_disponibles que llama
    a detectar_layout del mismo modulo.

    Argumentos:
        nombre:   Nombre tecnico del modulo a validar.
        contexto: Contexto del proyecto para detectar addons-path.

    Raises:
        typer.Exit(2): cuando el modulo no se encuentra y no es builtin.
    """
    validar_modulos([nombre], contexto, no_validate=False)


