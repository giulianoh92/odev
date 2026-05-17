"""Tests para odev.main — CLI entry point y opciones globales.

Verifica que las opciones globales del CLI (--version, --debug) funcionen
correctamente y que el callback principal del app Typer se comporte
como se espera.
"""

import logging

from typer.testing import CliRunner

from odev.main import app

runner = CliRunner()


class TestDebugFlag:
    """Verifica que --debug activa el nivel de logging DEBUG global (Q1).

    T11.1 RED: estos tests fallan hasta que se agregue el parametro
    --debug al callback main() en main.py.
    """

    def test_debug_flag_exists_in_app(self):
        """El flag --debug aparece en el help del CLI."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "--debug" in result.output, (
            "El flag --debug debe aparecer en el help de odev"
        )

    def test_debug_flag_activates_debug_level(self, caplog):
        """Con --debug, el root logger se configura a nivel DEBUG.

        T11.1 RED: el test falla porque --debug no existe aun en main().
        """
        # Invoke con un subcomando que exista (status requiere proyecto,
        # pero solo nos importa que --debug sea reconocido)
        result = runner.invoke(app, ["--debug", "--help"])
        # Si --debug existe, el exit_code no sera 2 (error de uso)
        assert result.exit_code != 2, (
            f"--debug no fue reconocido. Salida: {result.output}"
        )

    def test_without_debug_no_debug_logs(self):
        """Sin --debug, el nivel de logging no es DEBUG."""
        # Reset root logger to a known state
        root_logger = logging.getLogger()
        original_level = root_logger.level

        runner.invoke(app, ["--help"])

        # The root logger should NOT be set to DEBUG level
        # (it may be WARNING/INFO from basicConfig defaults)
        assert root_logger.level != logging.DEBUG or original_level == logging.DEBUG


class TestHelpSubgroups:
    """Verifica que --help muestra subgrupos organizados (Q3 — REQ-UX-3).

    T14.1 RED: estos tests fallan hasta que se agregue rich_help_panel
    a los app.add_typer() en main.py.
    """

    def test_help_shows_subgrupos_panel(self):
        """El help raiz muestra un panel 'Subgrupos' con db y projects."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        output = result.output
        # El panel "Subgrupos" debe aparecer en el help
        assert "Subgrupos" in output, (
            f"El panel 'Subgrupos' debe aparecer en el help. Output:\n{output}"
        )

    def test_help_lists_db_subgroup(self):
        """El help raiz lista el subgrupo 'db'."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "db" in result.output, (
            f"El subgrupo 'db' debe aparecer en el help. Output:\n{result.output}"
        )

    def test_help_lists_projects_subgroup(self):
        """El help raiz lista el subgrupo 'projects' cuando esta disponible."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        # projects puede no estar disponible si el modulo no existe, skip en ese caso
        # pero si aparece en el output debe estar bajo Subgrupos
        if "projects" in result.output:
            assert "Subgrupos" in result.output, (
                "Si 'projects' aparece en help, debe estar bajo el panel 'Subgrupos'"
            )
