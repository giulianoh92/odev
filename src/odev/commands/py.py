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

import re
import subprocess
import sys

import typer

from odev.commands._helpers import (
    obtener_docker,
    obtener_rutas,
    requerir_proyecto,
)
from odev.core.config import load_env
from odev.core.console import error

# Regex permisivo para lineas de banner del shell de Odoo.
# Cubre: lineas de log INFO/WARNING/ERROR/CRITICAL, el prompt 'odoo: db>',
# lineas de Python version, y lineas en blanco.
# Si este regex falla en una nueva version de Odoo, agregar el patron aqui
# y reportar como bug con la version afectada.
_BANNER_LINE_RE = re.compile(
    r"""
    ^\s*(?:
        \d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2},\d+   # timestamp log
        | Odoo\s+Server                                 # "Odoo Server X.0"
        | Loading\s+module                              # "Loading module X (N/M)"
        | Modules\s+loaded                              # "Modules loaded."
        | loading\s+modules                             # "loading modules for db:"
        | Python\s+\d+\.\d+                            # "Python 3.x..."
        | odoo:\s+\S+>                                  # "odoo: mydb>"
        | In\s+\[                                       # IPython prompt
    )
    """,
    re.VERBOSE,
)


def _strip_banner(raw: bytes) -> str:
    """Elimina lineas de banner del shell Odoo del stdout capturado.

    Mantiene la ultima linea no-banner (el resultado de la expresion print()).
    Las lineas vacias al inicio y fin se descartan.

    Args:
        raw: Bytes capturados de stdout del contenedor web.

    Returns:
        Resultado limpio (ultima linea no-banner).
    """
    text = raw.decode("utf-8", errors="replace")
    non_banner = [
        line
        for line in text.splitlines()
        if line.strip() and not _BANNER_LINE_RE.match(line)
    ]
    if not non_banner:
        return ""
    return non_banner[-1]


def _run_py(expression: str, keep_banner: bool = False) -> None:
    from odev.main import obtener_nombre_proyecto

    if not expression.strip():
        error("La expresion Python no puede estar vacia.")
        raise typer.Exit(2)

    contexto = requerir_proyecto(obtener_nombre_proyecto())
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
    # Usar exec_cmd con stdin_data (script es pequeno — no riesgo OOM).
    # exec_capture no acepta stdin; exec_cmd con interactive=False captura stdout/stderr.
    # exec_cmd lanza CalledProcessError en returncode != 0; capturamos aqui.
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

    if keep_banner:
        sys.stdout.buffer.write(stdout)
        raise typer.Exit(0)

    result_line = _strip_banner(stdout)
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
