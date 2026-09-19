"""Comando 'py': evalua una expresion Python en odoo shell.

El banner del shell de Odoo (lineas de log, prompt 'odoo: db>') se elimina
automaticamente del stdout. Solo la ultima linea no-banner (el resultado de
la expresion) se imprime.

Usar --keep-banner para conservar la salida raw (util para debug de banner
en nuevas versiones de Odoo). Si ves texto del banner en stdout, reportar
un bug indicando la version de Odoo — el regex necesita actualizacion.

Banner format varies across Odoo 16/17/18/19. If you see banner text in
stdout, file a bug with the Odoo version.

E1: odoo shell hace cr.rollback() al cerrar la consola, asi que las
escrituras ORM se descartan salvo que se pase --commit. Si la expresion
parece escribir (heuristica de texto: .create/.write/.unlink/.copy) y no se
paso --commit, se emite un warning por stderr antes de ejecutar — el
resultado en stdout, que los callers parsean, nunca se contamina con el
warning.
"""

from __future__ import annotations

import subprocess
import sys

import typer

from odev.commands._helpers import (
    obtener_docker,
    obtener_rutas,
    requerir_proyecto,
)
from odev.commands._odoo_shell import _BANNER_LINE_RE, _strip_banner  # noqa: F401
from odev.core.config import load_env
from odev.core.console import error
from odev.core.docker import USUARIO_ODOO

# E1: llamadas de escritura tipicas del ORM. Heuristica de texto sobre la
# expresion, no un analisis de AST — ver _expresion_parece_escribir.
_LLAMADAS_ESCRITURA = (".create(", ".write(", ".unlink(", ".copy(")


def _expresion_parece_escribir(expression: str) -> bool:
    """Heuristica estatica sobre el texto de la expresion (E1).

    Busca llamadas de escritura tipicas del ORM (.create(, .write(,
    .unlink(, .copy() en el texto de la expresion, sin parsear el AST ni
    entender el contexto. NO es una garantia: tiene falsos negativos (una
    escritura dentro de un metodo de negocio propio no se detecta) y podria
    en teoria tener falsos positivos. El objetivo es romper el silencio del
    caso dominante a costo minimo, no ser exhaustiva.

    Args:
        expression: Texto de la expresion tal cual la escribio el usuario.

    Returns:
        True si el texto contiene alguna llamada de escritura conocida.
    """
    return any(llamada in expression for llamada in _LLAMADAS_ESCRITURA)


def _advertir_si_escribe_sin_commit(expression: str, commit: bool) -> None:
    """Emite un warning por stderr si la expresion parece escribir sin --commit (E1).

    odoo shell hace cr.rollback() al cerrar la consola: sin --commit, cualquier
    escritura se descarta en silencio. Esta funcion rompe ese silencio con una
    advertencia — no bloquea la ejecucion, solo avisa. Se emite por stderr para
    no contaminar el resultado de la expresion, que se imprime en stdout y que
    los callers parsean.

    Args:
        expression: Texto de la expresion a evaluar.
        commit: True si se paso --commit (suprime el warning por completo).
    """
    if commit:
        return
    if not _expresion_parece_escribir(expression):
        return
    sys.stderr.write(
        "WARN: la expresion parece escribir (.create/.write/.unlink/.copy) y no "
        "se paso --commit.\n"
        "      odoo shell hace rollback al cerrar: los cambios se van a descartar. "
        "Usa --commit para persistirlos.\n"
    )


def _construir_script(expression: str, commit: bool) -> bytes:
    """Construye el script que se pipea por stdin a odoo shell.

    Siempre imprime el resultado de la expresion. Si commit=True, agrega una
    linea que ejecuta env.cr.commit() despues — asi el caller no tiene que
    escribir env.cr.commit() a mano dentro de la expresion (E1).

    Args:
        expression: Expresion Python a evaluar (una sola expresion).
        commit: Si True, commitea la transaccion despues de evaluar.

    Returns:
        Script codificado en utf-8, listo para pipear por stdin.
    """
    lineas = [f"print({expression})"]
    if commit:
        lineas.append("env.cr.commit()")
    return ("\n".join(lineas) + "\n").encode("utf-8")


def _execute_py(contexto, expression: str, commit: bool = False) -> str:
    """Pure data-return. No I/O, no exits. MCP-callable.

    Evaluates a Python expression in the Odoo shell and returns the
    banner-stripped result as a string.

    Args:
        contexto: Resolved ProjectContext.
        expression: Python expression to evaluate.
        commit: If True, commits the transaction (env.cr.commit()) after
            evaluating the expression. Default False keeps the existing
            behavior: odoo shell rolls back on close, discarding writes.

    Returns:
        Banner-stripped result string.

    Raises:
        ValueError: If expression is empty.
        RuntimeError: If the Odoo shell returns an error.
        subprocess.CalledProcessError: If the exec_cmd fails.
    """
    if not expression.strip():
        raise ValueError("La expresion Python no puede estar vacia.")

    rutas = obtener_rutas(contexto)
    valores_env = load_env(rutas.env_file)
    nombre_bd = valores_env.get("DB_NAME", "odoo_db")

    script = _construir_script(expression, commit)
    args = [
        "odoo",
        "shell",
        "--config=/etc/odoo/odoo.conf",
        "-d",
        nombre_bd,
        "--no-http",
    ]

    dc = obtener_docker(contexto)
    result = dc.exec_cmd("web", args, interactive=False, stdin_data=script, user=USUARIO_ODOO)
    stdout = result.stdout or b""
    stderr = result.stderr or b""
    returncode = result.returncode

    if returncode != 0 or (stderr and b"Traceback" in stderr):
        raise RuntimeError(stderr.decode("utf-8", errors="replace"))

    result_line = _strip_banner(stdout)
    return result_line if result_line else ""


def _run_py(expression: str, keep_banner: bool = False, commit: bool = False) -> None:
    from odev.main import obtener_nombre_proyecto

    if not expression.strip():
        error("La expresion Python no puede estar vacia.")
        raise typer.Exit(2)

    contexto = requerir_proyecto(obtener_nombre_proyecto())

    _advertir_si_escribe_sin_commit(expression, commit)

    if keep_banner:
        # keep_banner path needs raw stdout — run directly, not via _execute_py
        rutas = obtener_rutas(contexto)
        valores_env = load_env(rutas.env_file)
        nombre_bd = valores_env.get("DB_NAME", "odoo_db")
        script = _construir_script(expression, commit)
        args = [
            "odoo",
            "shell",
            "--config=/etc/odoo/odoo.conf",
            "-d",
            nombre_bd,
            "--no-http",
        ]
        dc = obtener_docker(contexto)
        try:
            result = dc.exec_cmd(
                "web", args, interactive=False, stdin_data=script, user=USUARIO_ODOO
            )
            stdout = result.stdout or b""
            stderr = result.stderr or b""
            returncode = result.returncode
        except subprocess.CalledProcessError as exc:
            sys.stderr.buffer.write(exc.stderr or b"")
            raise typer.Exit(exc.returncode) from exc
        if returncode != 0 or (stderr and b"Traceback" in stderr):
            sys.stderr.buffer.write(stderr)
            raise typer.Exit(1)
        sys.stdout.buffer.write(stdout)
        raise typer.Exit(0)

    # Normal path: delegate to _execute_py, then write result to stdout
    try:
        result_line = _execute_py(contexto, expression, commit=commit)
    except subprocess.CalledProcessError as exc:
        sys.stderr.buffer.write(exc.stderr or b"")
        raise typer.Exit(exc.returncode) from exc
    except RuntimeError as exc:
        sys.stderr.write(str(exc))
        raise typer.Exit(1) from exc
    if result_line:
        sys.stdout.write(result_line + "\n")
    raise typer.Exit(0)


def py(
    expression: str = typer.Argument(
        ...,
        help=(
            "Expresion Python a evaluar en odoo shell. "
            "Cuidado: side-effects ORM (.create/.write) NO se commitean por "
            "default; odoo shell hace cr.rollback() al cerrar. Pasar --commit "
            "para persistir, o terminar la expresion con env.cr.commit(). "
            "El banner de Odoo se elimina automaticamente del stdout."
        ),
    ),
    commit: bool = typer.Option(
        False,
        "--commit",
        help=(
            "Commitear la transaccion (env.cr.commit()) despues de evaluar la "
            "expresion. Sin este flag, odoo shell descarta los cambios al "
            "cerrar (comportamiento default, sin cambios). Tambien suprime el "
            "warning de escritura sin commit."
        ),
    ),
    keep_banner: bool = typer.Option(
        False,
        "--keep-banner",
        help="Conservar el banner del shell Odoo en stdout (para debug).",
    ),
) -> None:
    """Evalua una expresion en odoo shell y emite el resultado por stdout.

    El banner del shell de Odoo se elimina automaticamente. Solo el resultado
    de la expresion aparece en stdout.

    Por default, odoo shell hace cr.rollback() al cerrar: cualquier escritura
    ORM (.create/.write/.unlink/.copy) se descarta en silencio. Pasar --commit
    hace que odev commitee la transaccion despues de evaluar la expresion, sin
    que el caller tenga que escribir env.cr.commit() a mano.

    Si la expresion parece escribir (heuristica estatica sobre el texto:
    .create(, .write(, .unlink(, .copy() y no se paso --commit, se emite un
    warning por stderr antes de ejecutar, avisando que los cambios se van a
    descartar. Es una heuristica de texto, no una garantia: una escritura
    dentro de un metodo de negocio propio no se detecta. El warning se emite
    por stderr para no contaminar el resultado en stdout, que los callers
    parsean.

    Codigos de salida:

      0  Expresion evaluada sin errores

      1  Error en Odoo shell (excepcion Python, DB no disponible, etc.)

      2  Error de uso (expresion vacia)
    """
    _run_py(expression, keep_banner=keep_banner, commit=commit)
