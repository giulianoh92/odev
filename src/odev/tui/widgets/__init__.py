"""Widgets personalizados para la TUI de odev.

Contiene los componentes visuales del dashboard: panel de estado
de servicios, panel de informacion del proyecto y visor de logs
en tiempo real.
"""

from odev.tui.widgets.log_viewer import LogViewer
from odev.tui.widgets.project_info import ProjectInfoPanel
from odev.tui.widgets.status_panel import StatusPanel

__all__ = ["LogViewer", "ProjectInfoPanel", "StatusPanel"]
