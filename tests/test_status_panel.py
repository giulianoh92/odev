"""Tests para StatusPanel — widget TUI de estado de servicios.

Smoke tests que verifican la configuracion de columnas del panel sin
necesitar el runtime de Textual completo.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestStatusPanelColumns:
    """Verifica que StatusPanel define la columna 'Puertos' (Q9 — REQ-TUI-2).

    T18.1 RED: estos tests fallan hasta que se agregue la columna 'Puertos'
    en status_panel.py::on_mount().
    """

    def test_on_mount_adds_puertos_column(self) -> None:
        """on_mount() agrega la columna 'Puertos' a la DataTable.

        Smoke test: instancia StatusPanel con mocks de Textual y verifica
        que add_columns() recibe 'Puertos' como argumento.
        """
        from odev.tui.widgets.status_panel import StatusPanel

        panel = StatusPanel.__new__(StatusPanel)

        tabla_mock = MagicMock()
        panel._tabla = tabla_mock

        nombres_servicios_capturados = []

        def _init_nombres():
            panel._nombres_servicios = nombres_servicios_capturados

        # Parchear query_one y set_interval para evitar llamadas a Textual
        with (
            patch.object(StatusPanel, "query_one", return_value=tabla_mock),
            patch.object(StatusPanel, "set_interval"),
            patch.object(StatusPanel, "refresh_status"),
        ):
            panel.on_mount()

        # Verificar que add_columns fue llamado con 'Puertos'
        add_columns_calls = tabla_mock.add_columns.call_args_list
        assert add_columns_calls, "add_columns debe ser llamado en on_mount()"

        # Obtener todos los argumentos de la ultima llamada a add_columns
        args = add_columns_calls[0][0]  # args posicionales de la primera llamada
        assert "Puertos" in args, (
            f"La columna 'Puertos' debe agregarse en on_mount(). "
            f"Columnas actuales: {args}"
        )

    def test_puertos_column_is_fourth(self) -> None:
        """La columna 'Puertos' es la cuarta columna (indice 3)."""
        from odev.tui.widgets.status_panel import StatusPanel

        panel = StatusPanel.__new__(StatusPanel)
        tabla_mock = MagicMock()

        with (
            patch.object(StatusPanel, "query_one", return_value=tabla_mock),
            patch.object(StatusPanel, "set_interval"),
            patch.object(StatusPanel, "refresh_status"),
        ):
            panel.on_mount()

        args = tabla_mock.add_columns.call_args_list[0][0]
        assert len(args) >= 4, (
            f"Debe haber al menos 4 columnas. Columnas actuales: {args}"
        )
        assert args[3] == "Puertos", (
            f"La cuarta columna debe ser 'Puertos'. Columnas: {args}"
        )
