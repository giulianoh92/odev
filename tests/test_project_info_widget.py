"""Tests para el widget ProjectInfoPanel — informacion del proyecto en TUI.

Verifica REQ-DC-3: el widget muestra MAILHOG_PORT en lugar del
obsoleto LONGPOLL_PORT/PORT_LONGPOLL que fue retirado en Odoo 16+.
"""

from __future__ import annotations

import inspect
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestWidgetNoLongpoll:
    """Verifica que el widget no hace referencia a LONGPOLL_PORT ni PORT_LONGPOLL."""

    def test_widget_no_longpoll_references(self) -> None:
        """El widget no lee LONGPOLL_PORT ni PORT_LONGPOLL del .env.

        REQ-DC-3: referencias a longpoll eliminadas del widget.
        """
        import odev.tui.widgets.project_info as widget_mod

        fuente = inspect.getsource(widget_mod)

        assert "LONGPOLL_PORT" not in fuente, (
            "El widget no debe referenciar LONGPOLL_PORT (obsoleto desde Odoo 16+)"
        )
        assert "PORT_LONGPOLL" not in fuente, (
            "El widget no debe referenciar PORT_LONGPOLL (obsoleto desde Odoo 16+)"
        )
        assert "8072" not in fuente, (
            "El valor hardcodeado 8072 (longpoll fallback) debe ser eliminado"
        )

    def test_widget_shows_mailhog_row(self, tmp_path: Path) -> None:
        """El widget muestra una fila con el valor de MAILHOG_PORT del .env.

        REQ-DC-3 Scenario: TUI shows mailhog instead of dead longpoll.
        """
        from odev.tui.widgets.project_info import ProjectInfoPanel

        env_file = tmp_path / ".env"
        env_file.write_text(
            "PROJECT_NAME=test-project\nODOO_VERSION=18.0\n"
            "WEB_PORT=8069\nMAILHOG_PORT=8025\n"
        )

        # Mock ProjectPaths para apuntar al tmp_path
        mock_rutas = MagicMock()
        mock_rutas.env_file = env_file

        updated_content: list[str] = []

        def capture_update(content: str) -> None:
            updated_content.append(content)

        with (
            patch("odev.tui.widgets.project_info.ProjectPaths", return_value=mock_rutas),
        ):
            panel = ProjectInfoPanel.__new__(ProjectInfoPanel)
            panel.update = capture_update
            panel._actualizar_info()

        assert updated_content, "El widget debe llamar self.update() con algun contenido"
        contenido = updated_content[0]
        assert "Mailhog" in contenido or "mailhog" in contenido or "8025" in contenido, (
            f"El widget debe mostrar MAILHOG_PORT (8025). Contenido: {contenido!r}"
        )

    def test_widget_mailhog_fallback_when_absent(self, tmp_path: Path) -> None:
        """Sin MAILHOG_PORT en .env, el widget muestra un placeholder sin crashear.

        REQ-DC-3: si MAILHOG_PORT ausente -> placeholder, no crash.
        """
        from odev.tui.widgets.project_info import ProjectInfoPanel

        env_file = tmp_path / ".env"
        env_file.write_text("PROJECT_NAME=test-project\nODOO_VERSION=18.0\n")

        mock_rutas = MagicMock()
        mock_rutas.env_file = env_file

        updated_content: list[str] = []

        with (
            patch("odev.tui.widgets.project_info.ProjectPaths", return_value=mock_rutas),
        ):
            panel = ProjectInfoPanel.__new__(ProjectInfoPanel)
            panel.update = lambda content: updated_content.append(content)
            # No debe lanzar excepcion
            panel._actualizar_info()

        assert updated_content, "El widget debe renderizar incluso sin MAILHOG_PORT"
        # El widget no debe crashear ni mostrar 8072
        contenido = updated_content[0]
        assert "8072" not in contenido, (
            "El fallback hardcodeado 8072 no debe aparecer"
        )
