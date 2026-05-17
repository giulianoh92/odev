"""Helpers compartidos para comandos que ejecutan scripts en odoo shell.

Exporta _strip_banner y _BANNER_LINE_RE para uso desde py.py y model_info.py.
Extraido de commands/py.py en 0.5.1 para reutilizacion (ADR-6).
"""

from __future__ import annotations

import re

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
