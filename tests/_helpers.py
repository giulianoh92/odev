"""Helpers compartidos para tests que llaman comandos Typer directamente.

No es un modulo de fixtures (eso vive en conftest.py): estas funciones se
importan y se llaman directo desde el cuerpo de un test.
"""

from __future__ import annotations

import inspect
from typing import Any, Callable, TypeVar

import typer

T = TypeVar("T")

_SENTINEL_TYPES = (typer.models.OptionInfo, typer.models.ArgumentInfo)


def call_command(func: Callable[..., T], *args: Any, **overrides: Any) -> T:
    """Llama una funcion de comando Typer resolviendo los defaults reales.

    Llamar una funcion de comando Typer directamente en un test sin pasar
    todos sus parametros booleanos deja al parametro omitido con el objeto
    sentinel de typer.Option(...)/typer.Argument(...) como valor -- que es
    truthy, no False. Un test que omite un flag termina ejercitando la rama
    contraria a la que parece testear, y pasa igual.

    Esta funcion introspecciona la firma de `func` con `inspect` y, para
    cada parametro cuyo default sea una OptionInfo/ArgumentInfo de Typer,
    lo reemplaza por el `.default` real de ese objeto antes de invocar --
    el mismo valor que Typer le daria en la CLI si el flag no se paso. Los
    `overrides` explicitos del caller tienen prioridad sobre ese default
    resuelto.

    Argumentos:
        func: La funcion de comando Typer (el objeto decorado con
            @app.command, no una funcion interna _execute_*/_run_*).
        *args: Argumentos posicionales, pasados tal cual a func.
        **overrides: Argumentos explicitos que el caller quiere fijar;
            pisan el default resuelto de la firma para ese parametro.

    Returns:
        El valor de retorno de func(**kwargs) con todo resuelto por nombre.
    """
    firma = inspect.signature(func)
    # bind_partial mapea los posicionales/keywords ya dados por el caller a
    # su nombre de parametro real, para no pisarlos ni duplicarlos al
    # completar el resto con los defaults resueltos.
    ya_dados = firma.bind_partial(*args, **overrides)
    kwargs: dict[str, Any] = dict(ya_dados.arguments)

    for nombre, parametro in firma.parameters.items():
        if nombre in kwargs:
            continue
        default = parametro.default
        if isinstance(default, _SENTINEL_TYPES):
            kwargs[nombre] = default.default

    return func(**kwargs)
