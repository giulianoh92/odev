"""Comando 'doctor': diagnostica el entorno de desarrollo y reporta problemas.

Ejecuta una serie de verificaciones del sistema y del proyecto,
mostrando resultados con indicadores de color:
- [OK]   verde  -> todo correcto
- [WARN] amarillo -> advertencia, no bloqueante
- [FAIL] rojo   -> problema que impide el funcionamiento
- [INFO] azul   -> informacion adicional

En 0.4.0 se agrego: verificacion de MAILHOG_PORT, eliminacion del
_puerto_disponible local (ahora viene de odev.core.ports), y
_verificar_registry_puertos() para backfill y GC del registro.

En 0.5.1 se agrego: --json/-j flag para emitir resultados como JSON
(D1: dual-mode refactor — cada _verificar_* retorna CheckResult dict;
doctor() decide el modo de presentacion).

En 0.6.0 se agrego: resolucion de proyecto via requerir_proyecto (Path B)
en lugar de detect_mode(); los helpers _verificar_* reciben contexto
explicitamente; el path Rich degrada sin abortar.
"""

from __future__ import annotations

import json
import logging
import platform
import shutil
import subprocess
import sys
from typing import Any

import typer

from odev import __version__
from odev.core.console import console
from odev.core.ports import PORT_KEYS, puerto_disponible
from odev.core.resolver import ProjectContext

_logger = logging.getLogger(__name__)

# CheckResult shape (plain dict, not TypedDict — ADR-1):
# {
#     "name": str,          # e.g. "docker", "python", "registry-gc"
#     "status": "ok"|"warn"|"fail"|"info",
#     "message": str,       # human-readable single line
#     "hint": str | None,   # optional remediation hint
# }
CheckResult = dict[str, Any]


def _render_check(result: CheckResult) -> None:
    """Render a CheckResult dict using the existing Rich _imprimir_* helpers.

    Maps status -> appropriate printer. Prints hint as follow-up info line
    if present. Behavior is byte-identical to pre-0.5.1 Rich path.
    """
    status = result.get("status", "info")
    message = result.get("message", "")
    hint = result.get("hint")

    if status == "ok":
        _imprimir_ok(message)
    elif status == "warn":
        _imprimir_warn(message)
    elif status == "fail":
        _imprimir_fail(message)
    else:
        _imprimir_info(message)

    if hint:
        _imprimir_info(hint)


def _execute_doctor(contexto: ProjectContext | None) -> dict:
    """Pure data-return. No I/O, no exits. MCP-callable.

    Runs all doctor checks and returns the full result envelope as a dict.

    Args:
        contexto: Contexto del proyecto resuelto, o None para degradar checks
                  de proyecto a status 'info'.

    Returns:
        Dict matching the doctor JSON schema:
        {version, checks: [CheckResult], summary: {ok, warn, fail}, exit_code}
    """
    verificaciones = [
        _verificar_docker,
        _verificar_docker_compose,
        _verificar_python,
        _verificar_proyecto,
        _verificar_env,
        _ejecutar_registry_gc_y_backfill,
        _verificar_puertos,
        _verificar_docker_compose_file,
        _verificar_odoo_conf,
        _verificar_addons,
        _verificar_version_compatible,
    ]

    resultados: list[CheckResult] = []
    for verificacion in verificaciones:
        resultado = verificacion(contexto)
        if resultado is not None and isinstance(resultado, dict):
            resultados.append(resultado)

    summary: dict[str, int] = {"ok": 0, "warn": 0, "fail": 0}
    for r in resultados:
        status = r.get("status", "info")
        if status in summary:
            summary[status] += 1

    exit_code = 1 if summary["fail"] > 0 else 0
    return {
        "version": "0.6.2",
        "checks": resultados,
        "summary": summary,
        "exit_code": exit_code,
    }


def doctor(
    json_output: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Emite los resultados como un documento JSON en stdout (para agentes).",
    ),
) -> None:
    """Diagnostica el entorno de desarrollo y reporta problemas.

    Ejecuta verificaciones de Docker, Docker Compose, Python,
    proyecto detectado, archivos de configuracion, puertos
    disponibles y compatibilidad de version.

    Codigos de salida:

      0  Todas las verificaciones pasaron (o solo advertencias)

      1  Una o mas verificaciones fallaron
    """
    if json_output:
        # JSON gate: usa requerir_proyecto (Path B) para respetar --project y ODEV_PROJECT.
        # Si no se puede resolver, emite JSON de error a stderr y sale con codigo 1.
        from odev.commands._helpers import requerir_proyecto  # noqa: PLC0415
        from odev.main import obtener_nombre_proyecto  # noqa: PLC0415

        try:
            contexto: ProjectContext | None = requerir_proyecto(obtener_nombre_proyecto())
        except typer.Exit:
            sys.stderr.write(json.dumps({"error": "no project context"}) + "\n")
            raise typer.Exit(1) from None

        # JSON path: delega a _execute_doctor con el contexto resuelto (D1 design).
        # Rich console NO se llama en este path.
        envelope = _execute_doctor(contexto)
        sys.stdout.write(json.dumps(envelope) + "\n")
        raise typer.Exit(envelope["exit_code"])

    # Rich path: intenta resolver proyecto pero degrada sin abortar (ADR-3).
    from odev.commands._helpers import requerir_proyecto  # noqa: PLC0415
    from odev.main import obtener_nombre_proyecto  # noqa: PLC0415

    rich_contexto: ProjectContext | None
    try:
        rich_contexto = requerir_proyecto(obtener_nombre_proyecto())
    except typer.Exit:
        rich_contexto = None
        _imprimir_warn(
            "No se detecto proyecto odev (registry/cwd). Solo se ejecutaran chequeos de entorno."
        )

    console.print()
    console.print("[bold]Diagnostico del entorno odev[/]")
    console.print("=" * 40)
    console.print()

    # Orden: Docker → Compose → Python → proyecto → .env → GC registro →
    #         puertos → compose_file → odoo_conf → addons → version
    # El GC del registro (y backfill) debe correr ANTES que la verificacion
    # de puertos para que los orphans sean limpiados primero (REQ-UX-5).
    verificaciones = [
        _verificar_docker,
        _verificar_docker_compose,
        _verificar_python,
        _verificar_proyecto,
        _verificar_env,
        _ejecutar_registry_gc_y_backfill,
        _verificar_puertos,
        _verificar_docker_compose_file,
        _verificar_odoo_conf,
        _verificar_addons,
        _verificar_version_compatible,
    ]

    total_fallos = 0
    for verificacion in verificaciones:
        resultado = verificacion(rich_contexto)
        # Each _verificar_* now returns a CheckResult dict (0.5.1+).
        # _render_check handles the Rich presentation for each result.
        if isinstance(resultado, dict):
            _render_check(resultado)
            if resultado.get("status") == "fail":
                total_fallos += 1
        elif resultado is False:
            # Backward compat: legacy bool returns (should not happen in 0.5.1+)
            total_fallos += 1

    console.print()
    if total_fallos == 0:
        console.print("[bold green]Todas las verificaciones pasaron correctamente.[/]")
    else:
        console.print(
            f"[bold red]{total_fallos} verificacion(es) fallaron.[/] "
            "Revisa los errores marcados con [FAIL]."
        )


def _imprimir_ok(mensaje: str) -> None:
    """Imprime un resultado exitoso con indicador verde.

    Args:
        mensaje: Descripcion del chequeo exitoso.
    """
    console.print(f"  [bold green]\\[OK][/]   {mensaje}")


def _imprimir_warn(mensaje: str) -> None:
    """Imprime una advertencia con indicador amarillo.

    Args:
        mensaje: Descripcion de la advertencia.
    """
    console.print(f"  [bold yellow]\\[WARN][/] {mensaje}")


def _imprimir_fail(mensaje: str) -> None:
    """Imprime un fallo con indicador rojo.

    Args:
        mensaje: Descripcion del fallo.
    """
    console.print(f"  [bold red]\\[FAIL][/] {mensaje}")


def _imprimir_info(mensaje: str) -> None:
    """Imprime informacion adicional con indicador azul.

    Args:
        mensaje: Informacion adicional a mostrar.
    """
    console.print(f"  [bold blue]\\[INFO][/] {mensaje}")


def _verificar_docker(contexto: ProjectContext | None = None) -> CheckResult:
    """Verifica que Docker este instalado y funcionando.

    Args:
        contexto: Contexto del proyecto (no usado; parametro para uniformidad del dispatcher).

    Returns:
        CheckResult dict.
    """
    ruta_docker = shutil.which("docker")
    if ruta_docker is None:
        return {
            "name": "docker",
            "status": "fail",
            "message": "Docker no esta instalado o no esta en el PATH.",
            "hint": "Instala Docker Desktop o el paquete docker-ce.",
        }

    try:
        resultado = subprocess.run(
            ["docker", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if resultado.returncode == 0:
            version = resultado.stdout.strip()
            return {
                "name": "docker",
                "status": "ok",
                "message": f"Docker instalado ({version})",
                "hint": None,
            }
        else:
            return {
                "name": "docker",
                "status": "fail",
                "message": "Docker instalado pero no responde correctamente.",
                "hint": None,
            }
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return {
            "name": "docker",
            "status": "fail",
            "message": "Docker instalado pero no se pudo obtener la version.",
            "hint": None,
        }


def _verificar_docker_compose(contexto: ProjectContext | None = None) -> CheckResult:
    """Verifica que Docker Compose v2 este disponible.

    Args:
        contexto: Contexto del proyecto (no usado; parametro para uniformidad del dispatcher).

    Returns:
        CheckResult dict.
    """
    try:
        resultado = subprocess.run(
            ["docker", "compose", "version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if resultado.returncode == 0:
            version = resultado.stdout.strip()
            return {
                "name": "docker-compose",
                "status": "ok",
                "message": f"Docker Compose v2 disponible ({version})",
                "hint": None,
            }
        else:
            return {
                "name": "docker-compose",
                "status": "fail",
                "message": "Docker Compose v2 no esta disponible.",
                "hint": "Asegurate de tener Docker Desktop o el plugin 'docker-compose-plugin'.",
            }
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        msg = (
            "Docker Compose v2 no esta disponible. "
            "Asegurate de tener Docker Desktop o el plugin 'docker-compose-plugin'."
        )
        return {
            "name": "docker-compose",
            "status": "fail",
            "message": msg,
            "hint": None,
        }


def _verificar_python(contexto: ProjectContext | None = None) -> CheckResult:
    """Verifica la version de Python.

    Args:
        contexto: Contexto del proyecto (no usado; parametro para uniformidad del dispatcher).

    Returns:
        CheckResult dict.
    """
    version_python = platform.python_version()
    version_info = sys.version_info

    if version_info >= (3, 10):
        return {
            "name": "python",
            "status": "ok",
            "message": f"Python {version_python}",
            "hint": None,
        }
    else:
        msg = f"Python {version_python} (se requiere 3.10+). Actualiza tu version de Python."
        return {
            "name": "python",
            "status": "fail",
            "message": msg,
            "hint": "Actualiza Python a 3.10 o superior.",
        }


def _verificar_proyecto(contexto: ProjectContext | None = None) -> CheckResult:
    """Verifica si se detecta un proyecto odev.

    Args:
        contexto: Contexto del proyecto resuelto. Si None, reporta ausencia como INFO.

    Returns:
        CheckResult dict.
    """
    if contexto is None:
        msg = (
            "No se detecto proyecto odev en el directorio actual. "
            "Ejecuta 'odev init' para crear uno."
        )
        return {"name": "proyecto", "status": "info", "message": msg, "hint": None}

    nombre = contexto.nombre
    modo = contexto.modo
    # Distinguir legacy (ModoProyecto) del modo normal
    from odev.core.resolver import ModoProyecto  # noqa: PLC0415

    if modo == ModoProyecto.LEGACY:
        msg = (
            f"Proyecto legacy detectado: {nombre} (modo: {modo.value}). "
            "Ejecuta 'odev migrate' para migrar."
        )
        return {
            "name": "proyecto",
            "status": "warn",
            "message": msg,
            "hint": "Ejecuta 'odev migrate'.",
        }

    msg = f"Proyecto detectado: {nombre} (modo: {modo.value})"
    return {"name": "proyecto", "status": "ok", "message": msg, "hint": None}


def _verificar_env(contexto: ProjectContext | None = None) -> CheckResult:
    """Verifica si existe el archivo .env.

    Args:
        contexto: Contexto del proyecto resuelto. Si None, retorna INFO.

    Returns:
        CheckResult dict.
    """
    if contexto is None:
        msg = ".env: no se puede verificar sin un proyecto detectado."
        return {"name": "env", "status": "info", "message": msg, "hint": None}

    raiz = contexto.directorio_config
    ruta_env = raiz / ".env"
    if ruta_env.exists():
        return {"name": "env", "status": "ok", "message": ".env existe", "hint": None}
    else:
        msg = ".env no existe. Ejecuta 'odev init' para generar la configuracion."
        return {"name": "env", "status": "fail", "message": msg, "hint": "Ejecuta 'odev init'."}


def _verificar_docker_compose_file(contexto: ProjectContext | None = None) -> CheckResult:
    """Verifica si existe docker-compose.yml.

    Args:
        contexto: Contexto del proyecto resuelto. Si None, retorna INFO.

    Returns:
        CheckResult dict.
    """
    if contexto is None:
        msg = "docker-compose.yml: no se puede verificar sin un proyecto detectado."
        return {"name": "compose-file", "status": "info", "message": msg, "hint": None}

    raiz = contexto.directorio_config
    ruta_compose = raiz / "docker-compose.yml"
    if ruta_compose.exists():
        return {
            "name": "compose-file",
            "status": "ok",
            "message": "docker-compose.yml existe",
            "hint": None,
        }
    else:
        msg = "docker-compose.yml no existe. Ejecuta 'odev init' para generar la configuracion."
        return {
            "name": "compose-file",
            "status": "fail",
            "message": msg,
            "hint": "Ejecuta 'odev init'.",
        }


def _verificar_odoo_conf(contexto: ProjectContext | None = None) -> CheckResult:
    """Verifica si existe config/odoo.conf.

    Args:
        contexto: Contexto del proyecto resuelto. Si None, retorna INFO.

    Returns:
        CheckResult dict (warn if missing, ok if present).
    """
    if contexto is None:
        msg = "config/odoo.conf: no se puede verificar sin un proyecto detectado."
        return {"name": "odoo-conf", "status": "info", "message": msg, "hint": None}

    raiz = contexto.directorio_config
    ruta_conf = raiz / "config" / "odoo.conf"
    if ruta_conf.exists():
        return {
            "name": "odoo-conf",
            "status": "ok",
            "message": "config/odoo.conf existe",
            "hint": None,
        }
    else:
        msg = "config/odoo.conf no existe (se regenerara automaticamente con 'odev up')."
        return {"name": "odoo-conf", "status": "warn", "message": msg, "hint": None}


def _verificar_addons(contexto: ProjectContext | None = None) -> CheckResult:
    """Verifica el estado de los directorios de addons.

    Usa el resolver unificado para obtener todos los directorios de addons
    configurados y verificar su existencia y contenido.

    Args:
        contexto: Contexto del proyecto resuelto. Si None, retorna INFO.

    Returns:
        CheckResult dict.
    """
    if contexto is None:
        msg = "addons/: no se puede verificar sin un proyecto detectado."
        return {"name": "addons", "status": "info", "message": msg, "hint": None}

    from odev.commands._helpers import obtener_rutas  # noqa: PLC0415

    rutas = obtener_rutas(contexto)
    directorios_addons = rutas.addons_dirs

    cantidad_total = 0
    for directorio_addons in directorios_addons:
        if not directorio_addons.exists():
            continue

        # Contar modulos (subdirectorios con __manifest__.py)
        cantidad = 0
        for subdirectorio in directorio_addons.iterdir():
            if subdirectorio.is_dir() and (subdirectorio / "__manifest__.py").exists():
                cantidad += 1
        cantidad_total += cantidad

    if cantidad_total == 0 and not any(d.exists() for d in directorios_addons):
        return {
            "name": "addons",
            "status": "info",
            "message": "No se encontraron directorios de addons.",
            "hint": None,
        }
    return {
        "name": "addons",
        "status": "ok",
        "message": f"Addons: {cantidad_total} modulo(s) encontrado(s).",
        "hint": None,
    }


def _verificar_puertos(contexto: ProjectContext | None = None) -> CheckResult:
    """Verifica la disponibilidad de los puertos configurados.

    Lee los puertos del .env del proyecto y verifica si estan libres.

    Args:
        contexto: Contexto del proyecto resuelto. Si None, retorna INFO.

    Returns:
        CheckResult dict.
    """
    if contexto is None:
        msg = "Puertos: no se puede verificar sin un proyecto detectado."
        return {"name": "puertos", "status": "info", "message": msg, "hint": None}

    raiz = contexto.directorio_config
    # Intentar leer puertos del .env
    ruta_env = raiz / ".env"
    if not ruta_env.exists():
        msg = "Puertos: no se puede verificar sin archivo .env."
        return {"name": "puertos", "status": "info", "message": msg, "hint": None}

    from odev.core.config import load_env

    valores_env = load_env(ruta_env)

    # Puertos a verificar con sus nombres descriptivos
    puertos_a_verificar = {
        "WEB_PORT": "Odoo",
        "DB_PORT": "PostgreSQL",
        "PGWEB_PORT": "pgweb",
        "DEBUGPY_PORT": "debugpy",
        "MAILHOG_PORT": "Mailhog",
    }

    todos_disponibles = True
    for clave_env, nombre_servicio in puertos_a_verificar.items():
        valor_puerto = valores_env.get(clave_env)
        if valor_puerto is None:
            continue

        try:
            puerto = int(valor_puerto)
        except (ValueError, TypeError):
            continue

        if not puerto_disponible(puerto):
            todos_disponibles = False

    if todos_disponibles:
        return {
            "name": "puertos",
            "status": "ok",
            "message": "Todos los puertos disponibles.",
            "hint": None,
        }
    else:
        return {
            "name": "puertos",
            "status": "fail",
            "message": "Uno o mas puertos configurados estan en uso.",
            "hint": "Verifica que no haya otros proyectos odev corriendo en los mismos puertos.",
        }


# Q10: use PORT_KEYS from core/ports.py as single source of truth
_CLAVES_PUERTOS_BACKFILL = PORT_KEYS


def _verificar_registry_puertos(registry=None) -> dict:
    """Realiza GC y backfill del campo ports en el registro global.

    GC: Delega en registry.limpiar_obsoletos() que ya elimina entradas cuyo
    directorio_trabajo no existe — como efecto secundario, sus puertos quedan libres.

    Backfill: Para cada entrada con ports=None y directorio_trabajo existente,
    lee las 5 claves de puertos del .env y las escribe en el registro.
    Claves ausentes del .env se omiten; se emite warning para cada una faltante.

    Argumentos:
        registry: Instancia de Registry a usar. Si None, crea una nueva.

    Retorna:
        Diccionario con 'backfilleados' (lista de nombres) y 'eliminados' (lista de nombres).
    """
    if registry is None:
        from odev.core.registry import Registry

        registry = Registry()

    from odev.core.config import load_env

    # GC: eliminar entradas obsoletas (directorio no existe)
    eliminados = registry.limpiar_obsoletos()

    # Backfill: rellenar ports=None en entradas con directorio existente
    backfilleados: list[str] = []
    for entry in registry.listar():
        if entry.ports is not None:
            continue  # ya tiene puertos asignados

        ruta_env = entry.directorio_config / ".env"
        if not ruta_env.exists():
            # W2: do not call _imprimir_warn (leaks Rich to stdout in JSON mode).
            # These are internal backfill diagnostics; log at WARNING level instead.
            _logger.warning(
                "Proyecto '%s': no se puede hacer backfill (.env no encontrado en %s)",
                entry.nombre,
                entry.directorio_config,
            )
            continue

        valores_env = load_env(ruta_env)
        puertos_backfill: dict[str, int] = {}

        for clave in _CLAVES_PUERTOS_BACKFILL:
            valor = valores_env.get(clave)
            if valor is None:
                _logger.warning(
                    "Proyecto '%s': %s falta en .env — no se inventara el valor",
                    entry.nombre,
                    clave,
                )
                continue
            try:
                puertos_backfill[clave] = int(valor)
            except (ValueError, TypeError):
                _logger.warning(
                    "Proyecto '%s': %s=%r no es un entero valido — se omite",
                    entry.nombre,
                    clave,
                    valor,
                )

        if puertos_backfill:
            registry.asignar_puertos(entry.nombre, puertos_backfill)
            backfilleados.append(entry.nombre)

    return {"backfilleados": backfilleados, "eliminados": eliminados}


def _ejecutar_registry_gc_y_backfill(contexto: ProjectContext | None = None) -> CheckResult:
    """Ejecuta GC y backfill del registro de puertos como paso de doctor.

    # D1: JSON mode consolidates GC+backfill into a single info CheckResult; see sdd-design.

    Args:
        contexto: Contexto del proyecto (no usado; parametro para uniformidad del dispatcher).

    Returns:
        CheckResult dict (always info status).
    """
    try:
        resultado = _verificar_registry_puertos()
        eliminados = resultado["eliminados"]
        backfilleados = resultado["backfilleados"]

        # D1: JSON mode consolidates GC+backfill into a single info CheckResult; see sdd-design.
        n_eliminados = len(eliminados)
        n_backfill = len(backfilleados)
        msg = f"GC removed {n_eliminados} orphans; backfilled {n_backfill} entries"
        return {"name": "registry-gc", "status": "info", "message": msg, "hint": None}

    except Exception as exc:
        return {
            "name": "registry-gc",
            "status": "warn",
            "message": f"No se pudo verificar el registro de puertos: {exc}",
            "hint": None,
        }


def _verificar_version_compatible(contexto: ProjectContext | None = None) -> CheckResult:
    """Verifica compatibilidad de version entre el CLI y el proyecto.

    Lee odev_min_version de .odev.yaml y compara con la version instalada.

    Args:
        contexto: Contexto del proyecto resuelto. Si None, solo reporta la version instalada.

    Returns:
        CheckResult dict.
    """
    if contexto is None:
        msg = f"odev version {__version__}"
        return {"name": "version", "status": "info", "message": msg, "hint": None}

    from odev.core.resolver import ModoProyecto  # noqa: PLC0415

    if contexto.modo == ModoProyecto.LEGACY:
        msg = f"odev version {__version__} (proyecto legacy, sin verificacion de version)"
        return {"name": "version", "status": "info", "message": msg, "hint": None}

    raiz = contexto.directorio_config
    # Intentar leer la version minima del .odev.yaml o odev.yaml (external mode usa sin dot)
    ruta_yaml = raiz / ".odev.yaml"
    if not ruta_yaml.exists():
        ruta_yaml = raiz / "odev.yaml"
    if not ruta_yaml.exists():
        msg = f"odev version {__version__} (sin .odev.yaml para verificar)"
        return {"name": "version", "status": "info", "message": msg, "hint": None}

    try:
        from packaging.version import Version  # noqa: PLC0415

        from odev.core.project import ProjectConfig  # noqa: PLC0415

        config = ProjectConfig(raiz)
        version_minima = config.version_minima
        version_cli = Version(__version__)
        version_requerida = Version(version_minima)

        if version_cli >= version_requerida:
            msg = f"odev version {__version__} (minimo requerido: {version_minima})"
            return {"name": "version", "status": "ok", "message": msg, "hint": None}
        else:
            msg = (
                f"odev version {__version__} es menor a la requerida "
                f"por este proyecto ({version_minima}). "
                "Ejecuta: pip install --upgrade git+https://github.com/giulianoh92/odev.git"
            )
            return {
                "name": "version",
                "status": "warn",
                "message": msg,
                "hint": "pip install --upgrade git+https://github.com/giulianoh92/odev.git",
            }
    except (FileNotFoundError, Exception) as exc:
        msg = f"odev version {__version__} (no se pudo verificar compatibilidad: {exc})"
        return {"name": "version", "status": "warn", "message": msg, "hint": None}
