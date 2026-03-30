"""Proveedor de comandos para la paleta de comandos de la TUI.

Expone todos los comandos principales de odev en la paleta de comandos
de Textual (Ctrl+P), permitiendo buscar y ejecutar acciones rapidamente
sin recordar los atajos de teclado.
"""

from __future__ import annotations

from typing import AsyncGenerator

from textual.command import DiscoveryHit, Hit, Provider


class OdevCommandProvider(Provider):
    """Proveedor de comandos odev para la paleta de comandos de Textual.

    Expone las acciones principales (levantar, detener, reiniciar, shell,
    contexto y ayuda) en la paleta de comandos. Los comandos se pueden
    buscar por nombre o descripcion.
    """

    _COMANDOS: list[tuple[str, str, str]] = [
        ("Levantar servicios", "Ejecuta docker compose up -d", "action_up"),
        ("Detener servicios", "Ejecuta docker compose stop", "action_down"),
        ("Reiniciar servicio web", "Reinicia el contenedor web", "action_restart"),
        ("Abrir shell", "Sale a un shell interactivo (codigo 42)", "action_shell"),
        ("Generar contexto", "Genera PROJECT_CONTEXT.md del proyecto", "action_context"),
        ("Mostrar ayuda", "Abre la pantalla de atajos de teclado", "action_help"),
    ]

    async def search(self, query: str) -> AsyncGenerator[Hit, None]:
        """Busca comandos que coincidan con la consulta del usuario.

        Argumentos:
            query: Texto introducido por el usuario en la paleta.

        Yields:
            Hit por cada comando cuyo nombre o descripcion coincida.
        """
        consulta = query.lower()
        for nombre, descripcion, accion in self._COMANDOS:
            if consulta in nombre.lower() or consulta in descripcion.lower():
                yield Hit(
                    score=1.0,
                    match_display=nombre,
                    command=self._hacer_comando(accion),
                    help=descripcion,
                )

    async def discover(self) -> AsyncGenerator[DiscoveryHit, None]:
        """Expone todos los comandos disponibles cuando la paleta esta vacia.

        Yields:
            DiscoveryHit por cada comando registrado en _COMANDOS.
        """
        for nombre, descripcion, accion in self._COMANDOS:
            yield DiscoveryHit(
                display=nombre,
                command=self._hacer_comando(accion),
                help=descripcion,
            )

    def _hacer_comando(self, accion: str):
        """Crea un callable que ejecuta la accion en la app.

        Argumentos:
            accion: Nombre del metodo action_* de la app a invocar.

        Retorna:
            Callable asincrono que llama a la accion correspondiente.
        """
        async def _ejecutar() -> None:
            await self.app.run_action(accion)

        return _ejecutar
