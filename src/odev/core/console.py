"""Helpers de salida para la consola usando Rich.

Proporciona funciones de conveniencia para imprimir mensajes
con formato consistente: exito, error, advertencia e informacion.
"""

from rich.console import Console

console = Console()

# Los errores y advertencias van a stderr, no a stdout. stdout es el canal de
# datos: lo parsean los consumidores de --json y los pipes. Un mensaje de
# error o advertencia ahi rompe el parseo con un fallo que no tiene nada que
# ver con la causa real.
console_err = Console(stderr=True)


def success(message: str) -> None:
    """Imprime un mensaje de exito con indicador verde.

    Argumentos:
        message: Texto del mensaje a mostrar.
    """
    console.print(f"[bold green]OK[/] {message}")


def error(message: str) -> None:
    """Imprime un mensaje de error con indicador rojo, por stderr.

    Argumentos:
        message: Texto del mensaje de error a mostrar.
    """
    console_err.print(f"[bold red]ERROR[/] {message}")


def warning(message: str) -> None:
    """Imprime un mensaje de advertencia con indicador amarillo, por stderr.

    Argumentos:
        message: Texto de la advertencia a mostrar.
    """
    console_err.print(f"[bold yellow]WARN[/] {message}")


def info(message: str) -> None:
    """Imprime un mensaje informativo con indicador azul.

    Argumentos:
        message: Texto informativo a mostrar.
    """
    console.print(f"[bold blue]INFO[/] {message}")
