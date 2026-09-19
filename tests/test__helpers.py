"""Tests para tests/_helpers.py — el helper que resuelve el sentinel de Typer.

Llamar una funcion de comando Typer directamente sin pasar todos sus flags
deja el flag omitido con el objeto sentinel typer.Option(...)/Argument(...),
que es truthy -- no el default declarado. call_command() introspecciona la
firma real y resuelve cada flag omitido a su default declarado.
"""

from __future__ import annotations

import typer

from tests._helpers import call_command


def _comando_con_flag(
    activar: bool = typer.Option(False, "--activar", help="Activa algo."),
) -> bool:
    """Funcion de comando de juguete, con la misma forma que un comando Typer real."""
    return activar


def _comando_con_argumento(
    nombre: str = typer.Argument(..., help="Nombre requerido."),
    reintentar: bool = typer.Option(True, "--reintentar", help="Default en True."),
) -> tuple[str, bool]:
    return nombre, reintentar


class TestCallCommandResuelveSentinel:
    """El sentinel de Typer es truthy; call_command debe resolverlo al default real."""

    def test_flag_omitido_sin_helper_es_truthy(self) -> None:
        """Documenta el bug: llamar directo sin el flag da un sentinel truthy."""
        resultado = _comando_con_flag()
        assert resultado
        assert not isinstance(resultado, bool)

    def test_flag_omitido_con_helper_resuelve_a_false(self) -> None:
        """Con el helper, el flag omitido resuelve al default declarado (False)."""
        resultado = call_command(_comando_con_flag)
        assert resultado is False

    def test_override_explicito_pisa_el_default_resuelto(self) -> None:
        """Un override explicito del caller tiene prioridad sobre el default."""
        resultado = call_command(_comando_con_flag, activar=True)
        assert resultado is True

    def test_default_true_tambien_se_resuelve_correctamente(self) -> None:
        """Un Option con default True tambien se resuelve al valor real, no al sentinel."""
        _nombre, reintentar = call_command(_comando_con_argumento, "algo")
        assert reintentar is True

    def test_argumento_posicional_explicito_no_se_toca(self) -> None:
        """Un argumento posicional pasado por el caller no se reemplaza."""
        nombre, _reintentar = call_command(_comando_con_argumento, "mi-proyecto")
        assert nombre == "mi-proyecto"
