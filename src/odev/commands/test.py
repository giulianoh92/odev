"""Comando 'test': ejecuta tests de modulos Odoo.

Ejecuta los tests de un modulo especifico o de todos los modulos
usando el framework de tests nativo de Odoo. Soporta varios modos
de salida para consumo por agentes IA y pipelines CI.

Modos de salida:
| Flag          | Comportamiento                                          |
|---------------|---------------------------------------------------------|
| (ninguno+tty) | Stream crudo interactivo (comportamiento original)      |
| (ninguno-tty) | Auto-summary: conteo + duracion                         |
| --summary/-s  | Summary: conteo + nombres + duracion                    |
| --failures/-f | Solo bloques FAIL/ERROR con tracebacks                  |
| --json        | JSON estructurado en stdout (sin Rich)                  |
| --save-log    | Log crudo a archivo + summary en stdout                 |
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Optional

import typer

from odev.commands._helpers import (
    obtener_docker,
    obtener_rutas,
    parsear_modulos_csv,
    requerir_proyecto,
    validar_modulo_existe,  # noqa: F401  # re-exported for test mocks
    validar_modulos,
)
from odev.core.config import load_env
from odev.core.console import error, info
from odev.core.test_parser import TestResult, parse_odoo_test_output


def _stream_and_collect(
    popen: subprocess.Popen,
    save_log_path: Optional[Path] = None,
) -> tuple[list[str], int]:
    """Drena stdout de un Popen activo, opcionalmente guardando a archivo.

    Argumentos:
        popen:         Proceso Popen con stdout=PIPE.
        save_log_path: Si se provee, escribe el log crudo a este archivo.

    Retorna:
        Tupla (lineas_capturadas, returncode).
    """
    lines: list[str] = []
    log_file = None
    try:
        if save_log_path is not None:
            try:
                log_file = open(save_log_path, "w", encoding="utf-8")  # noqa: WPS515
            except OSError as exc:
                sys.stderr.write(f"ERROR: No se puede escribir en '{save_log_path}': {exc}\n")
                raise typer.Exit(1) from exc

        try:
            for raw_line in popen.stdout:
                line = raw_line.decode("utf-8", errors="replace")
                lines.append(line)
                if log_file is not None:
                    log_file.write(line)
        except KeyboardInterrupt:
            popen.terminate()
            try:
                popen.wait(timeout=2)
            except subprocess.TimeoutExpired:
                popen.kill()
            raise typer.Exit(1) from None
    finally:
        if log_file is not None:
            log_file.close()

    popen.wait()
    return lines, popen.returncode


def render_summary(result: TestResult) -> None:
    """Imprime un resumen de la corrida usando Rich.

    Incluye conteo de tests (passed/failed/errors) y duracion total.

    Argumentos:
        result: Resultado parseado de la corrida de tests.
    """
    from odev.core.console import console

    if result.parse_failed:
        sys.stderr.write("WARN: No se pudo parsear la salida; mostrando log crudo\n")
        sys.stdout.write(result.raw_output)
        return

    status = (
        "[bold green]OK[/]"
        if result.failed == 0 and result.errors == 0
        else "[bold red]FAIL[/]"
    )
    console.print(
        f"{status} {result.passed} passed, {result.failed} failed, "
        f"{result.errors} errors — {result.duration:.3f}s "
        f"({result.total} total)"
    )


def render_failures(result: TestResult) -> None:
    """Imprime solo los bloques FAIL/ERROR con sus tracebacks.

    Si no hay fallos, imprime indicacion de exito.

    Argumentos:
        result: Resultado parseado de la corrida de tests.
    """
    from odev.core.console import console

    if result.parse_failed:
        sys.stderr.write("WARN: No se pudo parsear la salida; mostrando log crudo\n")
        sys.stdout.write(result.raw_output)
        return

    if not result.failures:
        console.print("[bold green]OK[/] Todos los tests pasaron exitosamente.")
        return

    for failure in result.failures:
        label = "[bold red]FAIL[/]" if failure.kind == "FAIL" else "[bold yellow]ERROR[/]"
        cls_name = failure.test_class or "<loading>"
        mth_name = failure.method or "?"
        console.print(f"\n{label} {cls_name}.{mth_name}")
        if failure.traceback:
            console.print(failure.traceback)


def render_json(result: TestResult) -> None:
    """Escribe un objeto JSON en stdout. No usa Rich.

    Compatible con D1: la propiedad failures[] del parser ya contiene
    solo los failures/errors; passing tests no aparecen alli.

    Argumentos:
        result: Resultado parseado de la corrida de tests.
    """
    payload = {
        "total": result.total,
        "passed": result.passed,
        "failed": result.failed,
        "errors": result.errors,
        "duration": result.duration,
        "parse_failed": result.parse_failed,
        "raw_summary_line": result.raw_summary_line,
        "fallback_counters_used": result.fallback_counters_used,
        "failures": [
            {
                "class": f.test_class,
                "method": f.method,
                "kind": f.kind,
                "message": f.message,
                "traceback": f.traceback,
            }
            for f in result.failures
        ],
    }
    sys.stdout.write(json.dumps(payload) + "\n")


def _run_test(
    module: str,
    log_level: str,
    summary: bool,
    failures_only: bool,
    json_out: bool,
    tags: Optional[str],
    save_log: Optional[Path],
    no_validate: bool = False,
) -> None:
    """Implementacion principal del comando test.

    Separada del decorador Typer para facilitar tests unitarios directos.

    Argumentos:
        module:        Nombre(s) del modulo a testear, o 'all'. CSV soportado.
        log_level:     Nivel de log de Odoo.
        summary:       Si True, imprime resumen estructurado.
        failures_only: Si True, imprime solo bloques FAIL/ERROR.
        json_out:      Si True, emite JSON estructurado.
        tags:          Expresion de tags para --test-tags de Odoo (override/append).
        save_log:      Ruta donde guardar el log crudo.
        no_validate:   Si True, omite validacion contra addons-path.
    """
    from odev.main import obtener_nombre_proyecto

    contexto = requerir_proyecto(obtener_nombre_proyecto())

    # Pre-flight: parsear y validar modulo(s)
    modulos = parsear_modulos_csv(module)
    validar_modulos(modulos, contexto, no_validate=no_validate)

    rutas = obtener_rutas(contexto)

    valores_env = load_env(rutas.env_file)
    nombre_bd = valores_env.get("DB_NAME", "odoo_db")

    # `--no-http` evita que el proceso de test bindee un puerto interno.
    # Antes pasabamos `--http-port=$WEB_PORT`, pero cuando el proyecto
    # mapea WEB_PORT directo al 8069 interno (caso default), el odoo
    # principal del container ya lo ocupa y la corrida fallaba con
    # "Address already in use". Los tests TransactionCase/HttpCase de
    # Odoo no requieren un servidor HTTP externo — Odoo levanta uno
    # interno si hace falta.
    comando = [
        "odoo",
        "--test-enable",
        "--stop-after-init",
        "-d", nombre_bd,
        "--no-http",
        f"--log-level={log_level}",
    ]

    # Tags: construir --test-tags con prefijos /mod por modulo + user tags append
    tag_parts: list[str] = []
    if modulos != ["all"]:
        comando.extend(["-u", ",".join(modulos)])
        tag_parts.extend(f"/{m}" for m in modulos)
    if tags is not None:
        tag_parts.append(tags)
    if tag_parts:
        comando.extend(["--test-tags", ",".join(tag_parts)])

    dc = obtener_docker(contexto)

    # Determinar si usar modo stream o modo interactivo legacy
    use_stream = (
        json_out
        or failures_only
        or summary
        or save_log is not None
        or not sys.stdout.isatty()
    )

    if not use_stream:
        # Ruta legacy — interactiva, sin captura (comportamiento original)
        if module != "all":
            info(f"Ejecutando tests del modulo: {module}")
        else:
            info("Ejecutando todos los tests (esto puede tomar un rato)...")
        dc.exec_cmd("web", comando, interactive=True)
        return

    # Ruta con stream y parseo
    popen = dc.exec_cmd_stream("web", comando)
    lines, returncode = _stream_and_collect(popen, save_log_path=save_log)
    result = parse_odoo_test_output(lines)

    # Defensa en profundidad: si Odoo saly con 0 pero el parseo fallo
    # y el stream contiene "Address already in use" → forzar exit 3.
    # Con --no-http esto ya no deberia ocurrir, pero se mantiene por
    # si el modulo bajo test arranca su propio servidor.
    if returncode == 0 and result.parse_failed:
        if any("Address already in use" in ln for ln in lines):
            error("Puerto ocupado durante la ejecucion de Odoo (revisar test)")
            returncode = 3

    if json_out:
        # D1: --json + --failures son composables.
        # failures[] ya contiene solo fallos/errores (no passing tests)
        # por diseno del parser, por lo que la composicion es natural.
        render_json(result)
    elif failures_only:
        render_failures(result)
    else:
        # --summary explicito o auto-summary (no-tty sin flags)
        render_summary(result)

    raise typer.Exit(returncode)


def test(
    module: str = typer.Argument(
        ...,
        help=(
            "Modulo(s) a testear. CSV soportado: 'm1,m2'. "
            "'all' solo como token unico para ejecutar todos los tests."
        ),
    ),
    log_level: Optional[str] = typer.Option(
        "test",
        "--log-level",
        "-l",
        help="Nivel de log (test, debug, info, warn, error).",
    ),
    summary: bool = typer.Option(
        False,
        "--summary",
        "-s",
        help="Imprime resumen con conteo, nombres y duracion. Suprime el log crudo.",
    ),
    failures_only: bool = typer.Option(
        False,
        "--failures",
        "-f",
        help="Imprime solo bloques FAIL/ERROR con tracebacks.",
    ),
    json_out: bool = typer.Option(
        False,
        "--json",
        help="Emite JSON estructurado en stdout. Sin decoraciones Rich.",
    ),
    tags: Optional[str] = typer.Option(
        None,
        "--tags",
        help=(
            "Expresion de tags Odoo (ej. /mymod:MyClass o sale,account). "
            "Se agrega a los prefijos auto-generados /m1,/m2 como sufijo. "
            "Anula los prefijos si se usa sin modulos especificos."
        ),
    ),
    save_log: Optional[Path] = typer.Option(
        None,
        "--save-log",
        help="Ruta donde guardar el log crudo de Odoo.",
    ),
    no_validate: bool = typer.Option(
        False,
        "--no-validate",
        help="Omite la validacion previa de modulos contra addons-path.",
    ),
) -> None:
    """Ejecuta los tests de un modulo Odoo.

    Ejecuta los tests del modulo especificado usando el framework
    de tests de Odoo. Usa 'all' para ejecutar todos los tests
    disponibles (puede tomar bastante tiempo).

    Codigos de salida:

      0  Tests pasaron sin failures ni errores

      1  Hubo failures o errores en tests

      2  Error de uso (modulo no existe)

      3  Error de entorno (puerto ocupado, DB no disponible)

    Formato de --tags (Odoo --test-tags):

      /modulo:Clase           filtrar por clase

      /modulo:Clase.metodo   filtrar por metodo

      :metodo                 metodo en cualquier clase

      tag1,tag2              filtrar por @tagged()
    """
    _run_test(
        module=module,
        log_level=log_level or "test",
        summary=summary,
        failures_only=failures_only,
        json_out=json_out,
        tags=tags,
        save_log=save_log,
        no_validate=no_validate,
    )
