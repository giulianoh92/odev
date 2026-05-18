"""Comando 'py': evalua una expresion Python en odoo shell.

El banner del shell de Odoo (lineas de log, prompt 'odoo: db>') se elimina
automaticamente del stdout. Solo la ultima linea no-banner (el resultado de
la expresion) se imprime.

Usar --keep-banner para conservar la salida raw (util para debug de banner
en nuevas versiones de Odoo). Si ves texto del banner en stdout, reportar
un bug indicando la version de Odoo — el regex necesita actualizacion.

Banner format varies across Odoo 16/17/18/19. If you see banner text in
stdout, file a bug with the Odoo version.
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


def _execute_py(contexto, expression: str) -> str:
    """Pure data-return. No I/O, no exits. MCP-callable.

    Evaluates a Python expression in the Odoo shell and returns the
    banner-stripped result as a string.

    Args:
        contexto: Resolved ProjectContext.
        expression: Python expression to evaluate.

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

    script = f"print({expression})\n".encode("utf-8")
    args = [
        "odoo",
        "shell",
        "--config=/etc/odoo/odoo.conf",
        "-d",
        nombre_bd,
        "--no-http",
    ]

    dc = obtener_docker(contexto)
    result = dc.exec_cmd("web", args, interactive=False, stdin_data=script)
    stdout = result.stdout or b""
    stderr = result.stderr or b""
    returncode = result.returncode

    if returncode != 0 or (stderr and b"Traceback" in stderr):
        raise RuntimeError(stderr.decode("utf-8", errors="replace"))

    result_line = _strip_banner(stdout)
    return result_line if result_line else ""


def _run_py(expression: str, keep_banner: bool = False) -> None:
    from odev.main import obtener_nombre_proyecto

    if not expression.strip():
        error("La expresion Python no puede estar vacia.")
        raise typer.Exit(2)

    contexto = requerir_proyecto(obtener_nombre_proyecto())

    if keep_banner:
        # keep_banner path needs raw stdout — run directly, not via _execute_py
        rutas = obtener_rutas(contexto)
        valores_env = load_env(rutas.env_file)
        nombre_bd = valores_env.get("DB_NAME", "odoo_db")
        script = f"print({expression})\n".encode("utf-8")
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
            result = dc.exec_cmd("web", args, interactive=False, stdin_data=script)
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
        result_line = _execute_py(contexto, expression)
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
            "Cuidado: side-effects ORM (.create/.write) se commitean. "
            "El banner de Odoo se elimina automaticamente del stdout."
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

    Codigos de salida:

      0  Expresion evaluada sin errores

      1  Error en Odoo shell (excepcion Python, DB no disponible, etc.)

      2  Error de uso (expresion vacia)
    """
    _run_py(expression, keep_banner=keep_banner)
