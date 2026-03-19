"""Helpers de salida para la consola usando Rich.

Proporciona funciones de conveniencia para imprimir mensajes
con formato consistente: exito, error, advertencia e informacion.
"""

from rich.console import Console

console = Console()


def success(message: str) -> None:
    """Imprime un mensaje de exito con indicador verde.

    Args:
        message: Texto del mensaje a mostrar.
    """
    console.print(f"[bold green]OK[/] {message}")


def error(message: str) -> None:
    """Imprime un mensaje de error con indicador rojo.

    Args:
        message: Texto del mensaje de error a mostrar.
    """
    console.print(f"[bold red]ERROR[/] {message}")


def warning(message: str) -> None:
    """Imprime un mensaje de advertencia con indicador amarillo.

    Args:
        message: Texto de la advertencia a mostrar.
    """
    console.print(f"[bold yellow]WARN[/] {message}")


def info(message: str) -> None:
    """Imprime un mensaje informativo con indicador azul.

    Args:
        message: Texto informativo a mostrar.
    """
    console.print(f"[bold blue]INFO[/] {message}")
