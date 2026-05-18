"""Comando 'model-info': introspeccion de modelos Odoo via ORM en tiempo real.

Ejecuta un script Python en el shell de Odoo para obtener campos, herencia
y descripcion del modelo. Emite un documento JSON single-line a stdout.

Codigos de salida:

  0  Exito: modelo encontrado, JSON emitido a stdout
  1  Error de aplicacion (no hay proyecto, modelo no encontrado)
  3  Error de entorno (stack detenido, Docker falla)

Nota: este comando requiere que el stack este corriendo (odev up).
La salida de stdout es siempre una sola linea JSON, excepto con --pretty.
Para modelos grandes (account.move ~150 campos), JSON puede ser largo pero
no se trunca — Odoo shell usa stdout con buffer completo, no TTY.
"""

from __future__ import annotations

import json
import subprocess
import sys

import typer

from odev.commands._helpers import obtener_docker, requerir_proyecto
from odev.commands._odoo_shell import _strip_banner

# Python script template ejecutado en odoo shell.
# %r escapa el nombre del modelo de forma segura (string Python literal).
_MODEL_SCRIPT_TEMPLATE = """\
import json as _json
_model_name = %r
_m = env['ir.model'].search([('model', '=', _model_name)], limit=1)
if not _m:
    import sys as _sys
    _sys.stderr.write(_json.dumps({'error': 'Model not found: ' + _model_name}) + '\\n')
    raise SystemExit(1)
_fields_recs = env['ir.model.fields'].search([('model_id', '=', _m.id)])
_inherits = list(env[_m.model]._inherits.keys()) if _m.model in env else []
_payload = {
    'model': _m.model,
    'description': _m.name or '',
    'inherits': _inherits,
    'fields': [
        {
            'name': f.name,
            'type': f.ttype,
            'required': bool(f.required),
            'relation': f.relation or None,
        }
        for f in _fields_recs
    ],
}
print(_json.dumps(_payload))
"""


def _execute_model_info(contexto, model: str) -> dict:
    """Pure data-return. No I/O, no exits. MCP-callable.

    Introspects an Odoo model via ORM and returns its schema as a dict.

    Args:
        contexto: Resolved ProjectContext.
        model: Technical name of the Odoo model (e.g. res.partner).

    Returns:
        Dict with model/description/inherits/fields keys.

    Raises:
        ValueError: If the model is not found.
        RuntimeError: If the stack is not running or an unexpected error occurs.
        subprocess.CalledProcessError: If exec_cmd fails to start.
    """
    dc = obtener_docker(contexto)
    script = _MODEL_SCRIPT_TEMPLATE % model

    try:
        result = dc.exec_cmd(
            "web",
            ["odoo", "shell", "--no-http", "-d", "odoo"],
            stdin_data=script.encode("utf-8"),
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError("Stack not running or DB unavailable") from exc

    if result.returncode != 0:
        stderr_text = result.stderr.decode("utf-8", errors="replace") if result.stderr else ""
        if "Model not found" in stderr_text:
            raise ValueError(f"Model not found: {model}")
        raise RuntimeError("Stack not running or DB unavailable")

    payload_line = _strip_banner(result.stdout)
    if not payload_line:
        raise RuntimeError("No output from Odoo shell")

    try:
        data = json.loads(payload_line)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Failed to parse model output: {exc}") from exc

    return data


def model_info(
    model: str = typer.Argument(
        ...,
        help="Nombre tecnico del modelo Odoo (e.g. res.partner).",
    ),
    pretty: bool = typer.Option(
        False,
        "--pretty",
        help="Indenta el JSON para lectura humana.",
    ),
) -> None:
    """Introspecta un modelo Odoo y emite su esquema como JSON.

    Requiere que el stack este corriendo (odev up). Consulta el ORM
    en tiempo real para obtener todos los campos, incluyendo campos
    computados e heredados.

    Codigos de salida:

      0  Modelo encontrado, JSON emitido a stdout.

      1  No hay proyecto detectado, o el modelo no existe en el ORM.

      3  Stack detenido o Docker no disponible.
    """
    from odev.main import obtener_nombre_proyecto

    contexto = requerir_proyecto(obtener_nombre_proyecto())

    try:
        data = _execute_model_info(contexto, model)
    except ValueError as exc:
        sys.stderr.write(json.dumps({"error": str(exc)}) + "\n")
        raise typer.Exit(1) from exc
    except RuntimeError as exc:
        sys.stderr.write(json.dumps({"error": str(exc)}) + "\n")
        raise typer.Exit(3) from exc
    except subprocess.CalledProcessError as exc:
        sys.stderr.write(
            json.dumps({"error": "Stack not running or DB unavailable"}) + "\n"
        )
        raise typer.Exit(3) from exc

    if pretty:
        sys.stdout.write(json.dumps(data, indent=2) + "\n")
    else:
        sys.stdout.write(json.dumps(data) + "\n")
