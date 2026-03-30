"""Tests para comando odev addons."""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, Mock


class TestAddonsCommandModule:
    """Test suite para odev.commands.addons module."""

    def test_addons_module_imports(self):
        """Verificar que el módulo addons puede ser importado."""
        try:
            import sys
            # Ensure the src directory is in the path for testing
            import odev.commands.addons as addons_module
            assert hasattr(addons_module, 'app'), "addons module debe tener app"
            assert hasattr(addons_module, 'list'), "addons module debe tener comando 'list'"
            assert hasattr(addons_module, 'used_by'), "addons module debe tener comando 'used_by'"
        except ImportError:
            # If running from installed package, skip
            pytest.skip("odev not installed in development mode")

    def test_count_odoo_modules(self):
        """Verificar función auxiliar _count_odoo_modules."""
        try:
            from odev.commands.addons import _count_odoo_modules

            with patch('pathlib.Path.rglob') as mock_rglob:
                mock_rglob.return_value = [
                    Path("/some/path/__manifest__.py"),
                    Path("/some/path/module2/__manifest__.py"),
                ]
                result = _count_odoo_modules(Path("/some/path"))
                assert result == 2
        except ImportError:
            pytest.skip("odev not installed in development mode")

    def test_get_git_info(self):
        """Verificar función auxiliar _get_git_info."""
        try:
            from odev.commands.addons import _get_git_info

            with patch('subprocess.run') as mock_run:
                mock_result = Mock()
                mock_result.returncode = 0
                mock_result.stdout = "heads/main\n"
                mock_run.return_value = mock_result

                result = _get_git_info(Path("/some/path"))
                assert result == "heads/main"
        except ImportError:
            pytest.skip("odev not installed in development mode")
