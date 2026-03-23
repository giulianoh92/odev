"""Barra de referencia rapida de acciones disponibles.

Muestra un panel estatico con los atajos de teclado disponibles
en la TUI, facilitando la navegacion del usuario.
"""

from textual.widgets import Static


class ActionsBar(Static):
    """Panel de referencia de acciones rapidas por teclado.

    Renderiza un texto enriquecido con markup de Rich mostrando
    los atajos disponibles y sus acciones correspondientes.
    """

    def render(self) -> str:
        """Renderiza el contenido del panel con los atajos de teclado.

        Returns:
            Cadena con markup Rich describiendo las acciones disponibles.
        """
        return (
            "[bold]Acciones[/]\n\n"
            "[cyan]U[/] Levantar  [cyan]D[/] Detener\n"
            "[cyan]R[/] Reiniciar [cyan]S[/] Shell\n"
            "[cyan]C[/] Contexto  [cyan]Q[/] Salir\n"
        )
