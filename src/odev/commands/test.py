"""Comando 'test': ejecuta tests de modulos Odoo.

Ejecuta los tests de un modulo especifico o de todos los modulos
usando el framework de tests nativo de Odoo. Soporta varios modos
de salida para consumo por agentes IA y pipelines CI.

Modos de salida:
| Flag          | Comportamiento                                          |
|---------------|---------------------------------------------------------|
| (ninguno)     | Summary compacto: conteo + duracion (default, TTY o no) |
| --verbose/-v  | Stream crudo en vivo (comportamiento pre-0.7.0)         |
| --summary/-s  | Alias explicito del default (compat retro)              |
| --failures/-f | Solo bloques FAIL/ERROR con tracebacks                  |
| --json        | JSON estructurado en stdout (sin Rich)                  |
| --save-log    | Log crudo a archivo + summary en stdout                 |

--verbose es incompatible con --json/--summary/--failures (exit 2).

--changed reemplaza el argumento de modulo: toma los modulos tocados por el
diff de git (ver odev.core.changed_modules) y los corre por el mismo camino
que 'odev test m1,m2'.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path
from typing import NoReturn, Optional

import typer

from odev.commands._helpers import (
    MODULOS_BUILTIN,
    listar_modulos_disponibles,
    normalizar_exit_code_odoo,
    obtener_docker,
    obtener_rutas,
    parsear_modulos_csv,
    requerir_proyecto,
    resolver_addon_dir,
    validar_modulo_existe,  # noqa: F401  # re-exported for test mocks
    validar_modulos,
)
from odev.commands.sql import _execute_sql
from odev.core.changed_modules import (
    ModuloDetectado,
    dependientes_directos_instalados,
    detectar_modulos_cambiados,
)
from odev.core.config import load_env
from odev.core.console import error, info
from odev.core.docker import USUARIO_ODOO
from odev.core.test_parser import TestResult, parse_odoo_test_output

# Puerto HTTP interno que bindea el proceso de test dentro del container.
# Debe diferir del 8069 que ocupa el odoo principal. Odoo 19 ignora
# `--no-http` y sigue bindeando el puerto HTTP — sin este redirect el
# proceso de test crashea con "Address already in use". No tocar sin
# actualizar tests/test_test_cmd.py::TestHttpDisabled.
_TEST_HTTP_PORT = 8073


def _parse_test_target(raw: str) -> tuple[str, str | None]:
    """Split 'module:Class.method' into ('module', 'Class.method').

    Bare 'module' returns ('module', None). No colon: backward compat path.

    Reglas de uso (D8):
      - Un solo token con ':' → ('module', 'Class.method') o ('module', 'Class').
      - Sin ':' → ('module', None) — ruta backward-compat.
      - CSV + colon → RECHAZADO con ValueError.
        Ejemplo invalido: 'mod1,mod2:TestFoo.test_bar'
      - 'all:Class' → RECHAZADO con ValueError; el pseudo-modulo 'all'
        no soporta filtrado por clase.

    Funcion compartida entre CLI y MCP: senaliza con ValueError y deja que
    cada frontend decida como presentarlo. La CLI (_run_test) la convierte
    a stderr + typer.Exit(2); el path MCP (_execute_test) la deja propagar.

    Argumentos:
        raw: Token de modulo tal como lo entrega Typer.

    Retorna:
        Tupla (module_name, tag_suffix_or_None).

    Raises:
        ValueError: si la combinacion es invalida.
    """
    if ":" not in raw:
        return raw, None

    # Hay ':', validar que no sea CSV+colon
    module, _, tag = raw.partition(":")
    if "," in module:
        raise ValueError(
            "Shorthand ':Class.method' requiere un solo modulo destino; "
            "se recibio CSV. Usa --tags directamente para filtrar en multiples modulos."
        )

    if module == "all":
        raise ValueError(
            "El pseudo-modulo 'all' no soporta filtrado ':Class.method'. "
            "Usa --tags para filtrar por clase en todos los modulos."
        )

    return module, tag


def _build_test_tags(
    modulos: list[str],
    shorthand_tag: Optional[str],
    tags: Optional[str],
) -> list[str]:
    """Construye los specs para el flag --test-tags de Odoo.

    Odoo UNE los specs separados por coma, no los intersecta: en
    odoo/tests/tag_selector.py, check() hace any(...) sobre los includes, y
    dentro de un solo spec _is_matching() exige que coincida todo. Ademas un
    include sin tag toma 'standard' por default.

    Por eso emitir el prefijo auto-generado '/modulo' JUNTO a una expresion del
    usuario amplia la seleccion en vez de acotarla: '/mymod,alpha' significa
    "todos los tests standard de mymod" O "todos los tagueados alpha", y termina
    corriendo el modulo entero.

    Cuando el usuario pasa una expresion se descartan los prefijos: el argumento
    '-u <modulos>' ya limita que modulos corren tests, asi que la expresion sola
    filtra exactamente dentro de esos modulos.

    Argumentos:
        modulos: Lista de modulos parseada, o ["all"].
        shorthand_tag: Sufijo Clase.metodo de la forma 'modulo:Clase.metodo'.
        tags: Expresion cruda de --tags, si la hay.

    Retorna:
        Los specs a unir con comas. Vacio significa: no emitir --test-tags.

    Raises:
        ValueError: si se combinan el shorthand y --tags.
    """
    if shorthand_tag is not None and tags is not None:
        raise ValueError(
            "El shorthand 'modulo:Clase.metodo' y --tags no se pueden combinar: "
            "los dos definen el filtro de tests, y Odoo uniria ambos en vez de "
            "intersectarlos.\n"
            "Elegi uno: 'odev test modulo:Clase.metodo' o "
            "'odev test modulo --tags \"<expresion>\"'."
        )

    if tags is not None:
        # '-u' ya acota los modulos. Agregar '/modulo' aca haria OR con la
        # expresion del usuario y correria el modulo completo.
        return [tags]

    if modulos == ["all"]:
        return []

    if shorthand_tag is not None:
        return [f"/{modulos[0]}:{shorthand_tag}"]

    return [f"/{m}" for m in modulos]


def _validar_seleccion(
    module: Optional[str],
    changed: bool,
    base: Optional[str],
    with_dependents: bool,
) -> None:
    """Valida la combinacion de modulo explicito y --changed.

    Exactamente uno de los dos define que se testea; --base y
    --with-dependents solo tienen sentido con --changed. Funcion compartida
    entre CLI y MCP: senaliza con ValueError, igual que _parse_test_target.

    Argumentos:
        module:          Modulo(s) explicito(s), o None.
        changed:         Si se pidio --changed.
        base:            Referencia de --base, o None si no se paso.
        with_dependents: Si se pidio --with-dependents.

    Raises:
        ValueError: si la combinacion es invalida.
    """
    if module is not None and changed:
        raise ValueError(
            "El modulo explicito y --changed son excluyentes: --changed arma la "
            "lista de modulos a partir del diff de git. Usa uno de los dos."
        )
    if module is None and not changed:
        raise ValueError(
            "Falta el modulo a testear: indica 'odev test <modulo(s)>' o usa "
            "--changed para tomar los modulos tocados por el diff de git."
        )
    if not changed and (base is not None or with_dependents):
        raise ValueError("--base y --with-dependents solo se pueden usar junto con --changed.")


def _en_addons_path(modulo: ModuloDetectado, disponibles: set[str], contexto) -> bool:
    """True si el addons-path del proyecto resuelve el nombre a ESE directorio.

    Comparar solo el nombre no alcanza: un modulo homonimo fuera del
    addons-path (p.ej. una copia en vendor/) haria que '-u <nombre>' testee
    el otro, no el que cambio.
    """
    if modulo.nombre not in disponibles:
        return False
    addon_dir = resolver_addon_dir(modulo.nombre, contexto)
    return addon_dir is not None and addon_dir.resolve() == modulo.directorio


# Tope del detalle de un CalledProcessError en el mensaje: suficiente para la
# causa, sin volcar un log entero en stderr o en el ToolError.
_MAX_DETALLE_ERROR = 500


def _detalle_called_process_error(exc: subprocess.CalledProcessError) -> str:
    """Detalle legible de un CalledProcessError para un mensaje de error.

    El str() crudo es una linea de comando y un codigo: no dice nada. Lo util
    es lo que el proceso escribio, stderr primero y stdout despues. Si es muy
    largo se conserva el final, no el principio: docker compose suele
    anteponer WARNs (variables sin definir) y la causa real queda al final.
    Solo cuando los dos estan vacios queda la conjetura
    usual (stack caido): inventarla teniendo la causa real a mano disfrazaria
    un permiso denegado de stack caido.
    """
    for salida in (exc.stderr, exc.output):
        if not salida:
            continue
        texto = (
            salida.decode("utf-8", errors="replace") if isinstance(salida, bytes) else str(salida)
        ).strip()
        if texto:
            if len(texto) > _MAX_DETALLE_ERROR:
                texto = "..." + texto[-_MAX_DETALLE_ERROR:].lstrip()
            return f"{texto} (docker salio con {exc.returncode})"
    return (
        f"el stack no esta levantado o la DB no esta disponible (docker salio con {exc.returncode})"
    )


def _seleccionar_modulos_cambiados(
    contexto, base: Optional[str], with_dependents: bool
) -> tuple[list[str], list[str]]:
    """Resuelve la seleccion de --changed: modulos a testear y advertencias.

    Detecta los modulos tocados por el diff (git corre contra el directorio
    de trabajo del proyecto, donde vive el codigo), descarta los que no estan
    en el addons-path del proyecto y, con --with-dependents, suma los
    modulos instalados que dependen directamente de la seleccion. Todo lo que
    se descarta queda en las advertencias. Con layout desconocido (sin
    modulos disponibles) no se descarta nada: mismo fallback que
    validar_modulos, que asi nunca rechaza la seleccion despues.

    Funcion compartida entre CLI y MCP: no imprime ni sale. Las advertencias
    vuelven como datos para que cada frontend elija el canal.

    Argumentos:
        contexto:        Contexto del proyecto resuelto.
        base:            Referencia git para el merge-base, o None si no se
                         paso: el core la resuelve a HEAD, o al arbol vacio
                         en un repo sin commits.
        with_dependents: Si se suman los dependientes directos instalados.

    Retorna:
        Tupla (modulos sin duplicados y ordenados, advertencias).

    Raises:
        ValueError: si una `base` explicita no es una referencia valida.
        RuntimeError: sin git, fuera de un repo, o si la consulta de
            dependientes falla. Una consulta fallida siempre llega como
            RuntimeError con el contexto de --with-dependents, tambien
            cuando la causa es un CalledProcessError de docker (encadenado
            con 'from').
    """
    deteccion = detectar_modulos_cambiados(contexto.directorio_trabajo, base)
    advertencias = list(deteccion.advertencias)
    disponibles = listar_modulos_disponibles(contexto)

    seleccion: set[str] = set()
    for modulo in deteccion.modulos:
        if disponibles and not _en_addons_path(modulo, disponibles, contexto):
            advertencias.append(
                f"modulo '{modulo.nombre}' ({modulo.directorio}) no esta en el "
                "addons-path del proyecto, se omite."
            )
            continue
        seleccion.add(modulo.nombre)

    if with_dependents and seleccion:
        try:
            dependientes = dependientes_directos_instalados(
                seleccion, lambda consulta: _execute_sql(contexto, consulta)
            )
        except (RuntimeError, subprocess.CalledProcessError) as exc:
            detalle = (
                _detalle_called_process_error(exc)
                if isinstance(exc, subprocess.CalledProcessError)
                else str(exc)
            )
            raise RuntimeError(
                f"--with-dependents no pudo consultar los modulos instalados: {detalle}"
            ) from exc
        for nombre in dependientes:
            # Mismo criterio de aceptacion que validar_modulos.
            if disponibles and nombre not in disponibles and nombre not in MODULOS_BUILTIN:
                advertencias.append(
                    f"dependiente instalado '{nombre}' no esta en el addons-path "
                    "del proyecto, se omite."
                )
                continue
            seleccion.add(nombre)

    return sorted(seleccion), advertencias


def _rechazar(mensaje: str, json_out: bool, codigo: int) -> NoReturn:
    """Emite un diagnostico por stderr en el formato pedido y sale.

    Mismo criterio que el rechazo temprano de --verbose (C3): en modo --json
    el diagnostico va como JSON por stderr; si no, como texto plano por
    stderr (sin Rich: el mensaje puede traer refs o rutas con corchetes).
    """
    if json_out:
        sys.stderr.write(json.dumps({"error": mensaje}) + "\n")
    else:
        sys.stderr.write(f"{mensaje}\n")
    raise typer.Exit(codigo)


def _stream_and_collect(
    popen: subprocess.Popen,
    save_log_path: Optional[Path] = None,
    echo: bool = False,
) -> tuple[list[str], int]:
    """Drena stdout de un Popen activo, opcionalmente guardando a archivo.

    Argumentos:
        popen:         Proceso Popen con stdout=PIPE.
        save_log_path: Si se provee, escribe el log crudo a este archivo.
        echo:          Si True, re-emite cada linea a stdout en vivo
                       (modo --verbose con captura).

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
                if echo:
                    sys.stdout.write(line)
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
        "[bold green]OK[/]" if result.failed == 0 and result.errors == 0 else "[bold red]FAIL[/]"
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


def render_json(
    result: TestResult,
    process_exit_code: Optional[int],
    modulos: Optional[list[str]] = None,
) -> None:
    """Escribe un objeto JSON en stdout. No usa Rich.

    Compatible con D1: la propiedad failures[] del parser ya contiene
    solo los failures/errors; passing tests no aparecen alli.

    Argumentos:
        result: Resultado parseado de la corrida de tests.
        process_exit_code: Codigo crudo devuelto por el proceso Odoo, antes
            de cualquier normalizacion (0 en una corrida limpia). Un
            consumidor de --json necesita este valor para diagnosticar un
            proceso que murio por una causa que 'returncode_hint' no puede
            expresar (OOM killer, segfault): el campo 'returncode' del
            comando ya vino normalizado al contrato de exit codes, asi que
            sin este campo esa informacion se perderia. None (null en el
            JSON) solo cuando no se lanzo ningun proceso: --changed con
            seleccion vacia.
        modulos: Solo con --changed: la seleccion efectiva, que el caller
            no eligio y necesita conocer. None omite la clave, asi el payload
            de 'odev test m1,m2 --json' no cambia.
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
        "process_exit_code": process_exit_code,
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
    if modulos is not None:
        payload["modules"] = modulos
    sys.stdout.write(json.dumps(payload) + "\n")


def _resultado_a_dict(result: TestResult) -> dict:
    """Serializa un TestResult con el schema de _execute_test."""
    return {
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


def _execute_test(
    contexto,
    module: Optional[str] = None,
    tags: Optional[str] = None,
    no_validate: bool = False,
    changed: bool = False,
    base: Optional[str] = None,
    with_dependents: bool = False,
) -> dict:
    """Pure data-return. No I/O, no exits. MCP-callable.

    Runs Odoo tests for a module and returns the parsed TestResult as a dict.

    Args:
        contexto: Resolved ProjectContext.
        module: Module name(s) to test (CSV supported, or 'all'). Mutually
            exclusive with changed=True.
        tags: Optional Odoo test-tags expression.
        no_validate: If True, skip addons-path validation.
        changed: If True, test the modules touched by the git diff
            (merge-base(base, HEAD) vs the working tree, plus untracked
            files) through the same path as an explicit module list.
        base: Git ref for the merge-base with changed=True. None means the
            implicit HEAD, which falls back to the empty tree in a repo with
            no commits; an explicit ref never does.
        with_dependents: With changed=True, also test the installed modules
            that depend directly on the selection.

    Returns:
        Dict matching the TestResult JSON schema:
        {total, passed, failed, errors, duration, parse_failed,
         raw_summary_line, fallback_counters_used, failures[]}
        With changed=True it also carries 'modules' (the effective
        selection; empty means Odoo did not run) and 'warnings' (what was
        skipped): an MCP caller never sees stderr.

    Raises:
        ValueError: If module is empty, the combination is invalid, or the
            base ref does not resolve.
        RuntimeError: With changed=True, if git is missing, the project is
            not inside a git repository, or the dependents query fails
            (a docker CalledProcessError there is wrapped, never raised raw).
    """
    _validar_seleccion(module, changed, base, with_dependents)

    if changed:
        modulos_sel, advertencias = _seleccionar_modulos_cambiados(contexto, base, with_dependents)
        if modulos_sel:
            resultado = _execute_test(
                contexto, ",".join(modulos_sel), tags=tags, no_validate=no_validate
            )
        else:
            resultado = _resultado_a_dict(TestResult())
        return {**resultado, "modules": modulos_sel, "warnings": advertencias}

    module_name, shorthand_tag = _parse_test_target(module)
    modulos = parsear_modulos_csv(module_name)
    validar_modulos(modulos, contexto, no_validate=no_validate)

    rutas = obtener_rutas(contexto)
    valores_env = load_env(rutas.env_file)
    nombre_bd = valores_env.get("DB_NAME", "odoo_db")

    comando = [
        "odoo",
        "--test-enable",
        "--stop-after-init",
        "-d",
        nombre_bd,
        "--no-http",
        f"--http-port={_TEST_HTTP_PORT}",
        "--log-level=test",
    ]

    if modulos != ["all"]:
        comando.extend(["-u", ",".join(modulos)])

    tag_parts = _build_test_tags(modulos, shorthand_tag, tags)
    if tag_parts:
        comando.extend(["--test-tags", ",".join(tag_parts)])

    dc = obtener_docker(contexto)
    popen = dc.exec_cmd_stream("web", comando, user=USUARIO_ODOO)
    lines, _ = _stream_and_collect(popen)
    return _resultado_a_dict(parse_odoo_test_output(lines))


def _advertir_cero_tests(modulos: list[str], tag_parts: list[str]) -> None:
    """Avisa por stderr cuando la corrida ejecuto cero tests (A1-a).

    Un solo chequeo que cubre las causas usuales: un test_*.py no importado
    en tests/__init__.py, un nombre de modulo mal escrito que igual pasa la
    validacion de addons-path, o una expresion de --tags que no matchea
    nada. Un modulo legitimamente sin tests tambien cae aca, y es un caso
    valido: por eso esto es un warning por stderr, nunca un error ni un
    exit distinto de cero. Convertirlo en error rompe `odev test all`
    sobre un proyecto con modulos sin tests.

    Argumentos:
        modulos:   Modulo(s) efectivamente pasados a Odoo (o ['all']).
        tag_parts: Specs de --test-tags efectivamente pasados a Odoo.
    """
    filtro_tags = ",".join(tag_parts) if tag_parts else "(ninguno)"
    sys.stderr.write(
        "WARN: la corrida ejecuto 0 tests. "
        f"Filtro efectivo: modulos={','.join(modulos)}, --test-tags={filtro_tags}. "
        "Causas usuales: un test_*.py no importado en tests/__init__.py, "
        "un nombre de modulo mal escrito, o una expresion de --tags que no "
        "matcheo nada. Un modulo legitimamente sin tests tambien produce "
        "esto: no es un error.\n"
    )


def _lint_descubrimiento_tests(modulos: list[str], contexto) -> None:
    """Lint de descubrimiento: test_*.py huerfanos de tests/__init__.py (A1-b).

    Odoo solo descubre los modulos de test que tests/__init__.py importa
    explicitamente: get_test_modules() usa inspect.getmembers(mod,
    inspect.ismodule), y un submodulo solo es atributo del paquete si
    alguien lo importo. Un test_*.py que nadie importa aporta cero tests,
    sin error ni warning de Odoo.

    Parsea tests/__init__.py con `ast`, no con regex, para poder manejar
    'from . import a, b', 'from . import a' en lineas separadas, e imports
    dentro de condicionales (ast.walk recorre el arbol completo). Si el
    archivo no se puede parsear, omite el lint para ese modulo en silencio:
    un lint que reporta huerfanos falsos es peor que ningun lint.

    Se omite por completo cuando el destino es 'all'. Reusa
    resolver_addon_dir (misma resolucion de addons-path que validar_modulos)
    en vez de reimplementarla. Los builtins (MODULOS_BUILTIN) tambien se
    omiten: viven en el core de Odoo, no en el addons-path del proyecto,
    igual que el bypass que ya hace validar_modulos.

    Argumentos:
        modulos:  Lista de modulos destino (post parsear_modulos_csv).
        contexto: Contexto del proyecto resuelto.
    """
    if modulos == ["all"]:
        return

    for nombre in modulos:
        if nombre in MODULOS_BUILTIN:
            continue
        addon_dir = resolver_addon_dir(nombre, contexto)
        if addon_dir is None:
            continue

        tests_dir = addon_dir / "tests"
        if not tests_dir.is_dir():
            continue

        archivos_test = {p.stem for p in tests_dir.glob("test_*.py")}
        if not archivos_test:
            continue

        init_path = tests_dir / "__init__.py"
        if not init_path.is_file():
            continue

        try:
            arbol = ast.parse(init_path.read_text(encoding="utf-8"))
        except (SyntaxError, OSError, UnicodeDecodeError, ValueError):
            continue  # no se puede parsear: omitir en silencio, no adivinar

        importados: set[str] = set()
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.ImportFrom):
                if (nodo.level or 0) < 1:
                    continue  # import absoluto: no aplica al paquete tests/
                if nodo.module:
                    importados.add(nodo.module.split(".")[0])
                else:
                    for alias in nodo.names:
                        importados.add(alias.name.split(".")[0])
            elif isinstance(nodo, ast.Import):
                for alias in nodo.names:
                    importados.add(alias.name.split(".")[0])

        for huerfano in sorted(archivos_test - importados):
            sys.stderr.write(
                f"WARN: {tests_dir / f'{huerfano}.py'} existe pero no esta "
                f"importado en {init_path}. Odoo solo descubre modulos de "
                "test importados; este archivo va a aportar cero tests.\n"
            )


def _run_test(
    module: Optional[str],
    log_level: str,
    summary: bool,
    failures_only: bool,
    json_out: bool,
    tags: Optional[str],
    save_log: Optional[Path],
    no_validate: bool = False,
    verbose: bool = False,
    changed: bool = False,
    base: Optional[str] = None,
    with_dependents: bool = False,
) -> None:
    """Implementacion principal del comando test.

    Separada del decorador Typer para facilitar tests unitarios directos.

    Argumentos:
        module:        Nombre(s) del modulo a testear, o 'all'. CSV soportado.
                       None solo con --changed.
        log_level:     Nivel de log de Odoo.
        summary:       Si True, imprime resumen estructurado (alias del default).
        failures_only: Si True, imprime solo bloques FAIL/ERROR.
        json_out:      Si True, emite JSON estructurado.
        tags:          Expresion de tags para --test-tags de Odoo (override/append).
        save_log:      Ruta donde guardar el log crudo.
        no_validate:   Si True, omite validacion contra addons-path.
        verbose:       Si True, emite el stream crudo en vivo (pre-0.7.0).
                       Incompatible con json_out/summary/failures_only.
        changed:       Si True, los modulos salen del diff de git.
        base:          Referencia git para --changed (None: HEAD).
        with_dependents: Con --changed, suma los dependientes directos
                       instalados.
    """
    from odev.main import obtener_nombre_proyecto

    # --verbose contradice los modos parseados/compactos: rechazar temprano.
    # C3: el rechazo debe honrar el formato pedido. En modo --json el
    # diagnostico va como JSON por stderr; si no, error() ya escribe por
    # stderr y no rompe a un consumidor --json.
    if verbose and (json_out or summary or failures_only):
        mensaje = (
            "--verbose es incompatible con --json/--summary/--failures: "
            "el stream crudo no se parsea. Usa --verbose solo, o quita el flag."
        )
        if json_out:
            sys.stderr.write(json.dumps({"error": mensaje}) + "\n")
        else:
            error(mensaje)
        raise typer.Exit(2)

    try:
        _validar_seleccion(module, changed, base, with_dependents)
    except ValueError as exc:
        _rechazar(str(exc), json_out, 2)

    contexto = requerir_proyecto(obtener_nombre_proyecto())

    # --changed: la seleccion sale del diff y despues corre exactamente por el
    # mismo camino que 'odev test m1,m2'. La seleccion se anuncia por stderr:
    # stdout es el canal de datos.
    seleccion_changed: Optional[list[str]] = None
    if changed:
        # None (sin --base) llega asi al core: distingue la base implicita de
        # un '--base HEAD' explicito en un repo sin commits. 'referencia' es
        # solo para los mensajes.
        referencia = base if base is not None else "HEAD"
        try:
            seleccion_changed, advertencias = _seleccionar_modulos_cambiados(
                contexto, base, with_dependents
            )
        except ValueError as exc:
            _rechazar(str(exc), json_out, 2)
        except (RuntimeError, subprocess.CalledProcessError) as exc:
            # Sin git, fuera de un repo o DB no disponible: error de entorno.
            _rechazar(str(exc), json_out, 3)

        for advertencia in advertencias:
            sys.stderr.write(f"WARN: {advertencia}\n")

        alcance = f"base {referencia}" + (", con dependientes directos" if with_dependents else "")
        if not seleccion_changed:
            sys.stderr.write(
                f"INFO: --changed ({alcance}) no encontro modulos para testear; "
                "no se ejecuta Odoo.\n"
            )
            if json_out:
                render_json(TestResult(), None, modulos=[])
            raise typer.Exit(0)

        module = ",".join(seleccion_changed)
        sys.stderr.write(
            f"INFO: --changed ({alcance}) selecciono {len(seleccion_changed)} modulo(s): {module}\n"
        )

    try:
        # D8: detectar shorthand 'module:Class.method' antes de parsear CSV.
        # _parse_test_target valida y rechaza combinaciones invalidas
        # (CSV+colon, 'all:Class') con ValueError.
        module_name, shorthand_tag = _parse_test_target(module)

        # Pre-flight: parsear y validar modulo(s)
        # Si habia shorthand, el module_name es el modulo limpio (sin ":...")
        modulos = parsear_modulos_csv(module_name)
        validar_modulos(modulos, contexto, no_validate=no_validate)
    except ValueError as exc:
        # A2: las funciones compartidas senalizan con ValueError; la CLI es
        # la que decide presentarlo como stderr + exit 2.
        sys.stderr.write(f"{exc}\n")
        raise typer.Exit(2) from exc

    # A1-b: lint de descubrimiento antes de lanzar Odoo. Solo advierte por
    # stderr, nunca bloquea la corrida.
    _lint_descubrimiento_tests(modulos, contexto)

    rutas = obtener_rutas(contexto)

    valores_env = load_env(rutas.env_file)
    nombre_bd = valores_env.get("DB_NAME", "odoo_db")

    # Odoo 19 ignora `--no-http` y sigue bindeando el puerto HTTP default
    # (8069 interno), lo que colisiona con el odoo principal del container
    # → "Address already in use". `--http-port=8073` redirige el bind del
    # proceso de test a un puerto interno libre. Se mantiene `--no-http`
    # para Odoo <=18 donde si era suficiente. Ver _TEST_HTTP_PORT module-level.
    comando = [
        "odoo",
        "--test-enable",
        "--stop-after-init",
        "-d",
        nombre_bd,
        "--no-http",
        f"--http-port={_TEST_HTTP_PORT}",
        f"--log-level={log_level}",
    ]

    if modulos != ["all"]:
        comando.extend(["-u", ",".join(modulos)])

    try:
        tag_parts = _build_test_tags(modulos, shorthand_tag, tags)
    except ValueError as exc:
        sys.stderr.write(f"{exc}\n")
        raise typer.Exit(2) from exc
    if tag_parts:
        comando.extend(["--test-tags", ",".join(tag_parts)])

    dc = obtener_docker(contexto)

    # Desde 0.7.0 el summary compacto es el default SIEMPRE (TTY o no).
    # --verbose restaura el stream crudo: sin --save-log usa la ruta
    # interactiva original; con --save-log streamea con echo + captura.
    if verbose and save_log is None:
        if module != "all":
            info(f"Ejecutando tests del modulo: {module}")
        else:
            info("Ejecutando todos los tests (esto puede tomar un rato)...")
        dc.exec_cmd("web", comando, interactive=True, user=USUARIO_ODOO)
        return

    # Ruta con stream y parseo
    popen = dc.exec_cmd_stream("web", comando, user=USUARIO_ODOO)
    lines, returncode = _stream_and_collect(popen, save_log_path=save_log, echo=verbose)
    result = parse_odoo_test_output(lines)

    # Se preserva el codigo crudo del proceso ANTES de cualquier mapeo:
    # normalizar_exit_code_odoo() y el caso puerto-ocupado de abajo pisan
    # 'returncode', y este valor es el unico canal (mensaje de stderr +
    # 'process_exit_code' del JSON) por el que ese numero sigue siendo
    # visible para un caller una vez terminado el comando.
    codigo_proceso = returncode

    # Defensa en profundidad: si Odoo salio con 0 pero el parseo fallo
    # y el stream contiene "Address already in use" → forzar exit 3.
    # Con --no-http esto ya no deberia ocurrir, pero se mantiene por
    # si el modulo bajo test arranca su propio servidor. Este 3 lo decide
    # odev mismo (no viene del proceso), asi que queda fuera del mapeo
    # generico de mas abajo.
    puerto_ocupado = False
    if returncode == 0 and result.parse_failed:
        if any("Address already in use" in ln for ln in lines):
            error("Puerto ocupado durante la ejecucion de Odoo (revisar test)")
            returncode = 3
            puerto_ocupado = True

    # Contrato de exit codes: Odoo 19 con --test-enable --stop-after-init
    # devuelve 0 aunque haya tests fallidos, asi que un proceso en 0 deriva
    # el codigo final del resultado parseado (returncode_hint: 1 si hay
    # failures/errors/parse_failed). El puerto ocupado ya quedo resuelto
    # arriba y sobrevive tal cual. Cualquier otro codigo de proceso (137 del
    # OOM killer, 139 de un segfault, lo que sea) no tiene lugar en el
    # contrato (0/1/2/3) que EPILOG_EXIT_CODES publica, asi que se normaliza
    # con el mismo mapeo que 'addon-install' y 'update' — unico punto de
    # verdad, ver normalizar_exit_code_odoo().
    if returncode == 0:
        returncode = result.returncode_hint
    elif not puerto_ocupado:
        codigo_normalizado = normalizar_exit_code_odoo(returncode)
        if codigo_normalizado != returncode:
            modulos_csv = ",".join(modulos)
            mensaje = (
                f"Ejecucion de tests de '{modulos_csv}' termino con errores: "
                f"odev reporta un fallo de runtime (exit {codigo_normalizado}); "
                f"el proceso Odoo devolvio el codigo {returncode}."
            )
            error(mensaje)
        returncode = codigo_normalizado

    # A1-a: 0 tests ejecutados es indistinguible de exito si nadie avisa.
    # Warning por stderr, nunca error: nunca cambia returncode ni contamina
    # stdout (donde --json espera JSON puro).
    if result.total == 0 and not result.parse_failed:
        _advertir_cero_tests(modulos, tag_parts)

    if json_out:
        # D1: --json + --failures son composables.
        # failures[] ya contiene solo fallos/errores (no passing tests)
        # por diseno del parser, por lo que la composicion es natural.
        render_json(result, codigo_proceso, modulos=seleccion_changed)
    elif failures_only:
        render_failures(result)
    elif not verbose:
        # --summary explicito o summary compacto default (0.7.0)
        render_summary(result)
    # verbose + save_log: el log crudo ya se emitio en vivo via echo

    raise typer.Exit(returncode)


def test(
    module: Optional[str] = typer.Argument(
        None,
        help=(
            "Modulo(s) a testear. CSV soportado: 'm1,m2'. "
            "'all' solo como token unico para ejecutar todos los tests. "
            "Obligatorio salvo con --changed, con el que es excluyente."
        ),
    ),
    log_level: Optional[str] = typer.Option(
        "test",
        "--log-level",
        "-l",
        help="Nivel de log (test, debug, info, warn, error).",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help=(
            "Emite el stream crudo de Odoo en vivo (comportamiento pre-0.7.0). "
            "Incompatible con --json/--summary/--failures."
        ),
    ),
    summary: bool = typer.Option(
        False,
        "--summary",
        "-s",
        help=(
            "Imprime resumen con conteo y duracion. Desde 0.7.0 es el "
            "comportamiento default; el flag se mantiene por compatibilidad."
        ),
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
            "Expresion de tags Odoo (ej. MyClass, sale, :TestFoo.test_bar). "
            "REEMPLAZA los prefijos auto-generados /m1,/m2 en vez de sumarse a "
            "ellos: los modulos ya quedan acotados por -u, y unir ambos haria "
            "que Odoo corra el modulo entero. No combinable con el shorthand "
            "'modulo:Clase.metodo'."
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
    changed: bool = typer.Option(
        False,
        "--changed",
        help=(
            "Testea los modulos tocados por el diff de git: lo que difiere "
            "entre merge-base(--base, HEAD) y el working tree, mas los "
            "untracked no ignorados. Excluyente con el argumento de modulo."
        ),
    ),
    base: Optional[str] = typer.Option(
        None,
        "--base",
        help=(
            "Con --changed: referencia git para el merge-base (ej. main). "
            "Default: HEAD, es decir solo el trabajo sin commitear."
        ),
    ),
    with_dependents: bool = typer.Option(
        False,
        "--with-dependents",
        help=(
            "Con --changed: suma los modulos instalados que dependen directamente de la seleccion."
        ),
    ),
) -> None:
    """Ejecuta los tests de un modulo Odoo.

    Ejecuta los tests del modulo especificado usando el framework
    de tests de Odoo. Usa 'all' para ejecutar todos los tests
    disponibles (puede tomar bastante tiempo).

    Con --changed (en vez del modulo) testea los modulos tocados por el
    diff de git; --with-dependents suma sus dependientes directos
    instalados. Seleccion vacia: avisa por stderr y sale con 0.

    Por default imprime un resumen compacto (conteo + duracion).
    Usa --verbose/-v para ver el log crudo de Odoo en vivo.

    Codigos de salida:

      0  Tests pasaron sin failures ni errores

      1  Hubo failures o errores en tests, o el proceso Odoo murio

      2  Error de uso (modulo no existe, ref de --base invalida)

      3  Error de entorno (puerto ocupado, DB no disponible, sin git)

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
        verbose=verbose,
        changed=changed,
        base=base,
        with_dependents=with_dependents,
    )
