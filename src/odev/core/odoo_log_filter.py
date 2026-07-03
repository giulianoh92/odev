"""Filtro de log de Odoo para los modos compactos de update/addon-install.

Reduce el log crudo de una corrida `odoo -u/-i ... --stop-after-init` a
las lineas relevantes para el usuario:

  - lineas con nivel WARNING/ERROR/CRITICAL,
  - bloques de traceback completos (con su contexto),
  - la linea final de exito de Odoo ("Modules loaded.").

Funcion pura, sin I/O: los comandos deciden que hacer con el resultado.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Optional

# Prefijo de timestamp en logs Odoo: "2026-07-03 10:00:00,001 1 LEVEL ..."
RE_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}\s")

# Linea con nivel de log relevante: "... <pid> WARNING|ERROR|CRITICAL ..."
RE_NIVEL_RELEVANTE = re.compile(
    r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3} \d+ (WARNING|ERROR|CRITICAL)\b"
)

# Inicio de un bloque de traceback Python
RE_TRACEBACK_START = re.compile(r"Traceback \(most recent call last\):")

# Linea final de exito de Odoo al cargar modulos. "Modules loaded." es el
# marcador estable en v14-v19; "Registry loaded in X.XXXs" queda como
# fallback (se emite inmediatamente despues) y no pisa al marcador primario.
RE_SUCCESS_PRIMARIO = re.compile(r"Modules loaded\.")
RE_SUCCESS_FALLBACK = re.compile(r"Registry loaded in [\d.]+s")


@dataclass
class FilteredOdooLog:
    """Resultado del filtrado de un log de update/install.

    Campos:
        relevant_lines: Lineas WARNING/ERROR/CRITICAL + bloques traceback.
        success_line:   Linea de exito de Odoo (None si no aparecio).
        has_traceback:  True si el log contiene al menos un traceback.
        has_critical:   True si hay al menos una linea CRITICAL.
    """

    relevant_lines: list[str] = field(default_factory=list)
    success_line: Optional[str] = None
    has_traceback: bool = False
    has_critical: bool = False

    @property
    def returncode_hint(self) -> int:
        """Codigo de salida sugerido segun el contenido del log.

        Retorna:
            1 si hay traceback o CRITICAL (fallo real aunque el proceso
            haya salido con 0); 0 en caso contrario. WARNING no falla.
        """
        return 1 if (self.has_traceback or self.has_critical) else 0


def filter_odoo_log(lines: Iterable[str]) -> FilteredOdooLog:
    """Filtra el log crudo de Odoo dejando solo lo relevante.

    Maquina de estados simple: en modo normal detecta lineas con nivel
    relevante y el inicio de tracebacks; dentro de un traceback acumula
    todo hasta la proxima linea con timestamp (fin del bloque).

    Argumentos:
        lines: Lineas del log (con o sin newline final; se normalizan).

    Retorna:
        FilteredOdooLog con lineas relevantes, exito y flags de fallo.
    """
    resultado = FilteredOdooLog()
    en_traceback = False

    for raw in lines:
        line = raw.rstrip("\n")

        if en_traceback:
            if RE_TIMESTAMP.match(line):
                # Una linea timestampeada cierra el bloque de traceback;
                # se re-procesa abajo como linea normal.
                en_traceback = False
            else:
                resultado.relevant_lines.append(line)
                continue

        match_nivel = RE_NIVEL_RELEVANTE.match(line)
        if match_nivel:
            resultado.relevant_lines.append(line)
            if match_nivel.group(1) == "CRITICAL":
                resultado.has_critical = True
            continue

        if RE_TRACEBACK_START.search(line):
            resultado.has_traceback = True
            resultado.relevant_lines.append(line)
            en_traceback = True
            continue

        if RE_SUCCESS_PRIMARIO.search(line):
            resultado.success_line = line
        elif resultado.success_line is None and RE_SUCCESS_FALLBACK.search(line):
            resultado.success_line = line

    return resultado
