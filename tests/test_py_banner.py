"""Tests para odev py — banner strip del shell Odoo.

Cubre:
  - C7-1: banner stripped for Odoo 16/17/18/19 fixtures
  - C7-3: --keep-banner preserves raw output

Usa fixtures en tests/fixtures/odoo_banners/odoo_{16,17,18,19}.txt
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import typer

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "odoo_banners"

# Expected result values embedded in each fixture (last non-empty, non-banner line)
EXPECTED_RESULTS = {
    "odoo_16.txt": "42",
    "odoo_17.txt": "hello",
    "odoo_18.txt": "world",
    "odoo_19.txt": "result_value",
}


def _make_contexto(tmp_path: Path) -> MagicMock:
    """Crea un ProjectContext mock con directorio temporal."""
    ctx = MagicMock()
    ctx.directorio_config = tmp_path
    ctx.nombre = "test-project"
    ctx.config = MagicMock()
    ctx.config.rutas_addons = None
    return ctx


def _make_exec_cmd_result(stdout: bytes, stderr: bytes = b"", returncode: int = 0):
    """Crea un CompletedProcess mock para exec_cmd."""
    import subprocess
    return subprocess.CompletedProcess(
        args=[],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


def _call_run_py_with_banner(
    tmp_path: Path,
    mock_dc: MagicMock,
    expression: str = "2+2",
    keep_banner: bool = False,
    env_valores: dict | None = None,
):
    """Llama _run_py con keep_banner y contexto mockeado.

    Nota: py usa exec_cmd (con stdin_data) para pasar el script,
    no exec_capture (que no acepta stdin).
    """
    from odev.commands.py import _run_py

    ctx = _make_contexto(tmp_path)
    env = env_valores if env_valores is not None else {"DB_NAME": "odoo_db"}

    with (
        patch("odev.commands.py.requerir_proyecto", return_value=ctx),
        patch("odev.commands.py.obtener_docker", return_value=mock_dc),
        patch("odev.commands.py.obtener_rutas") as mock_rutas,
        patch("odev.commands.py.load_env", return_value=env),
        patch("odev.main.obtener_nombre_proyecto", return_value="test-project"),
    ):
        mock_rutas.return_value.env_file = tmp_path / ".env"
        try:
            _run_py(expression, keep_banner=keep_banner)
        except (SystemExit, typer.Exit) as e:
            return e
    return None


# ---------------------------------------------------------------------------
# TestPyBannerStrip (Spec C7-1) — parametrized over Odoo 16/17/18/19
# ---------------------------------------------------------------------------


class TestPyBannerStrip:
    """Banner de Odoo shell es eliminado del stdout por defecto."""

    @pytest.mark.parametrize("fixture_file", ["odoo_16.txt", "odoo_17.txt", "odoo_18.txt", "odoo_19.txt"])
    def test_banner_stripped_en_fixture(self, tmp_path: Path, capsys, fixture_file: str) -> None:
        """C7-1: solo la linea resultado aparece en stdout (banner eliminado)."""
        fixture_path = FIXTURES_DIR / fixture_file
        raw_output = fixture_path.read_bytes()
        expected = EXPECTED_RESULTS[fixture_file]

        mock_dc = MagicMock()
        # py usa exec_cmd con stdin_data para pasar el script al shell Odoo
        mock_dc.exec_cmd.return_value = _make_exec_cmd_result(raw_output)

        _call_run_py_with_banner(tmp_path, mock_dc, "any_expression")

        captured = capsys.readouterr()
        stdout = captured.out.strip()
        assert stdout == expected, (
            f"Fixture {fixture_file}: expected {expected!r}, got {stdout!r}. "
            f"Full stdout: {captured.out!r}"
        )

    def test_keep_banner_preserva_salida_raw(self, tmp_path: Path, capsys) -> None:
        """C7-3: --keep-banner → salida raw sin stripping."""
        fixture_path = FIXTURES_DIR / "odoo_16.txt"
        raw_output = fixture_path.read_bytes()

        mock_dc = MagicMock()
        mock_dc.exec_cmd.return_value = _make_exec_cmd_result(raw_output)

        _call_run_py_with_banner(tmp_path, mock_dc, "any_expression", keep_banner=True)

        captured = capsys.readouterr()
        # Con --keep-banner, el stdout debe contener lineas del banner
        assert "Odoo Server" in captured.out or "odoo.modules" in captured.out or "Loading module" in captured.out
