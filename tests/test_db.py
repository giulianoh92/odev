"""Tests para odev.commands.db — operaciones de base de datos.

Cubre los subcomandos snapshot, restore, list y anonymize.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestRestoreStreaming:
    """Verifica que db restore NO carga el dump completo en RAM.

    Spec C2-1: large dump stays within memory bounds.
    Design D2: usa exec_cmd_file con stdin_file=ruta_archivo.
    """

    @pytest.fixture
    def contexto(self, tmp_path):
        """Prepara contexto de proyecto y snapshot de prueba."""
        # Crea un archivo de snapshot falso
        snapshots_dir = tmp_path / "snapshots"
        snapshots_dir.mkdir()
        dump_file = snapshots_dir / "mi_backup_20260101_120000.dump"
        dump_file.write_bytes(b"fake dump content")
        return tmp_path, snapshots_dir, dump_file

    def test_restore_usa_exec_cmd_file_con_stdin_file(self, contexto, tmp_path):
        """restore llama a exec_cmd_file con stdin_file=ruta_archivo.

        Verifica que NO se llama read_bytes() sobre el dump path —
        el contenido se pipea directamente via exec_cmd_file.
        """
        _tmp, snapshots_dir, dump_file = contexto

        mock_dc = MagicMock()
        mock_dc.exec_cmd_file.return_value = MagicMock(returncode=0, stdout=b"", stderr=b"")
        mock_dc.exec_cmd.return_value = MagicMock(returncode=0, stdout=b"", stderr=b"")

        mock_context = MagicMock()
        mock_rutas = MagicMock()
        mock_rutas.snapshots_dir = snapshots_dir
        mock_rutas.env_file = tmp_path / ".env"
        (tmp_path / ".env").write_text("DB_USER=odoo\nDB_NAME=odoo_db\n")

        with (
            patch("odev.commands.db.requerir_proyecto", return_value=mock_context),
            patch("odev.commands.db.obtener_rutas", return_value=mock_rutas),
            patch("odev.commands.db.load_env", return_value={"DB_USER": "odoo", "DB_NAME": "odoo_db"}),
            patch("odev.commands.db.obtener_docker", return_value=mock_dc),
            patch("odev.main.obtener_nombre_proyecto", return_value="test-project"),
            patch("odev.commands.db.typer.confirm", return_value=True),
        ):
            from odev.commands.db import restore

            restore("mi_backup")

        # exec_cmd_file DEBE haberse llamado con stdin_file=dump_file
        mock_dc.exec_cmd_file.assert_called_once()
        call_kwargs = mock_dc.exec_cmd_file.call_args
        # El kwarg stdin_file debe ser la ruta al dump
        assert call_kwargs.kwargs.get("stdin_file") == dump_file or (
            len(call_kwargs.args) >= 3 and call_kwargs.args[2] == dump_file
        )

    def test_restore_no_llama_read_bytes_en_dump(self, contexto, tmp_path, monkeypatch):
        """read_bytes() NO se llama sobre el archivo dump durante restore.

        El streaming via exec_cmd_file evita cargar el dump en RAM.
        """
        _tmp, snapshots_dir, dump_file = contexto

        read_bytes_llamado = []

        original_read_bytes = Path.read_bytes

        def mock_read_bytes(self):
            if self == dump_file:
                read_bytes_llamado.append(self)
            return original_read_bytes(self)

        mock_dc = MagicMock()
        mock_dc.exec_cmd_file.return_value = MagicMock(returncode=0, stdout=b"", stderr=b"")
        mock_dc.exec_cmd.return_value = MagicMock(returncode=0, stdout=b"", stderr=b"")

        mock_context = MagicMock()
        mock_rutas = MagicMock()
        mock_rutas.snapshots_dir = snapshots_dir
        mock_rutas.env_file = tmp_path / ".env"
        (tmp_path / ".env").write_text("DB_USER=odoo\nDB_NAME=odoo_db\n")

        with (
            patch("odev.commands.db.requerir_proyecto", return_value=mock_context),
            patch("odev.commands.db.obtener_rutas", return_value=mock_rutas),
            patch("odev.commands.db.load_env", return_value={"DB_USER": "odoo", "DB_NAME": "odoo_db"}),
            patch("odev.commands.db.obtener_docker", return_value=mock_dc),
            patch("odev.main.obtener_nombre_proyecto", return_value="test-project"),
            patch("odev.commands.db.typer.confirm", return_value=True),
            patch.object(Path, "read_bytes", mock_read_bytes),
        ):
            from odev.commands.db import restore

            restore("mi_backup")

        assert read_bytes_llamado == [], (
            f"read_bytes() fue llamado sobre el dump: {read_bytes_llamado}"
        )
