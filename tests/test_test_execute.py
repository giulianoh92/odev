"""RED tests for _execute_test(contexto, module, tags=None) -> dict.

C6-R1: helper returns TestResult dict without Typer side effects.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def _make_contexto(tmp_path) -> MagicMock:
    ctx = MagicMock()
    ctx.directorio_config = tmp_path
    ctx.nombre = "test-project"
    ctx.config = MagicMock()
    ctx.config.rutas_addons = None
    return ctx


_DEFAULT_ENV = {"DB_NAME": "odoo_db", "DB_USER": "odoo"}

# Minimal Odoo test output that produces a parseable TestResult
_TEST_OUTPUT_OK = [
    "Ran 1 test in 0.123s\n",
    "OK\n",
]

_TEST_OUTPUT_FAIL = [
    "FAIL: TestMyModule.test_something\n",
    "Ran 1 test in 0.456s\n",
    "FAILED (failures=1)\n",
]


def _make_popen_mock(lines, returncode=0):
    """Create a mock Popen with iterable stdout."""
    mock_popen = MagicMock()
    mock_popen.stdout = [line.encode() for line in lines]
    mock_popen.returncode = returncode
    mock_popen.wait.return_value = returncode
    return mock_popen


class TestExecuteTest:
    """_execute_test returns TestResult dict, no stdout."""

    def test_happy_path_returns_dict_with_required_keys(self, tmp_path) -> None:
        """Returns dict with total/passed/failed/errors/duration keys."""
        from odev.commands.test import _execute_test

        mock_popen = _make_popen_mock(_TEST_OUTPUT_OK, returncode=0)
        mock_dc = MagicMock()
        mock_dc.exec_cmd_stream.return_value = mock_popen

        ctx = _make_contexto(tmp_path)
        with (
            patch("odev.commands.test.obtener_docker", return_value=mock_dc),
            patch("odev.commands.test.obtener_rutas") as mock_rutas,
            patch("odev.commands.test.load_env", return_value=_DEFAULT_ENV),
            patch("odev.commands.test.validar_modulos"),
        ):
            mock_rutas.return_value.env_file = tmp_path / ".env"
            result = _execute_test(ctx, "my_module")

        assert isinstance(result, dict)
        for key in ("total", "passed", "failed", "errors", "duration"):
            assert key in result, f"Expected key '{key}' in result"

    def test_no_stdout_side_effect(self, tmp_path, capsys) -> None:
        """_execute_test must not write to stdout."""
        from odev.commands.test import _execute_test

        mock_popen = _make_popen_mock(_TEST_OUTPUT_OK, returncode=0)
        mock_dc = MagicMock()
        mock_dc.exec_cmd_stream.return_value = mock_popen

        ctx = _make_contexto(tmp_path)
        with (
            patch("odev.commands.test.obtener_docker", return_value=mock_dc),
            patch("odev.commands.test.obtener_rutas") as mock_rutas,
            patch("odev.commands.test.load_env", return_value=_DEFAULT_ENV),
            patch("odev.commands.test.validar_modulos"),
        ):
            mock_rutas.return_value.env_file = tmp_path / ".env"
            _execute_test(ctx, "my_module")

        captured = capsys.readouterr()
        assert captured.out == ""

    def test_no_typer_exit_raised(self, tmp_path) -> None:
        """_execute_test does NOT raise typer.Exit on success."""
        import typer

        from odev.commands.test import _execute_test

        mock_popen = _make_popen_mock(_TEST_OUTPUT_OK, returncode=0)
        mock_dc = MagicMock()
        mock_dc.exec_cmd_stream.return_value = mock_popen

        ctx = _make_contexto(tmp_path)
        raised = False
        try:
            with (
                patch("odev.commands.test.obtener_docker", return_value=mock_dc),
                patch("odev.commands.test.obtener_rutas") as mock_rutas,
                patch("odev.commands.test.load_env", return_value=_DEFAULT_ENV),
                patch("odev.commands.test.validar_modulos"),
            ):
                mock_rutas.return_value.env_file = tmp_path / ".env"
                _execute_test(ctx, "my_module")
        except typer.Exit:
            raised = True

        assert not raised, "_execute_test must not raise typer.Exit"

    def test_with_tags_passes_tags_to_result(self, tmp_path) -> None:
        """Tags parameter is accepted without error."""
        from odev.commands.test import _execute_test

        mock_popen = _make_popen_mock(_TEST_OUTPUT_OK, returncode=0)
        mock_dc = MagicMock()
        mock_dc.exec_cmd_stream.return_value = mock_popen

        ctx = _make_contexto(tmp_path)
        with (
            patch("odev.commands.test.obtener_docker", return_value=mock_dc),
            patch("odev.commands.test.obtener_rutas") as mock_rutas,
            patch("odev.commands.test.load_env", return_value=_DEFAULT_ENV),
            patch("odev.commands.test.validar_modulos"),
        ):
            mock_rutas.return_value.env_file = tmp_path / ".env"
            result = _execute_test(ctx, "my_module", tags="/my_module:MyClass")

        assert isinstance(result, dict)


class TestExecuteTestChanged:
    """changed=True: la seleccion sale del diff; sin I/O ni typer.Exit."""

    def _patches(self, tmp_path, mock_dc, seleccion=None):
        return (
            patch("odev.commands.test.obtener_docker", return_value=mock_dc),
            patch(
                "odev.commands.test.obtener_rutas", **{"return_value.env_file": tmp_path / ".env"}
            ),
            patch("odev.commands.test.load_env", return_value=_DEFAULT_ENV),
            patch("odev.commands.test.validar_modulos"),
            patch(
                "odev.commands.test._seleccionar_modulos_cambiados",
                return_value=seleccion if seleccion is not None else ([], []),
            ),
        )

    def test_seleccion_no_vacia_corre_esos_modulos(self, tmp_path) -> None:
        from odev.commands.test import _execute_test

        mock_dc = MagicMock()
        mock_dc.exec_cmd_stream.return_value = _make_popen_mock(_TEST_OUTPUT_OK)
        ctx = _make_contexto(tmp_path)
        p_docker, p_rutas, p_env, p_validar, p_sel = self._patches(
            tmp_path, mock_dc, (["mod_a", "mod_b"], ["WARN de prueba"])
        )
        with p_docker, p_rutas, p_env, p_validar, p_sel as mock_sel:
            result = _execute_test(ctx, changed=True, base="main", with_dependents=True)
            mock_sel.assert_called_once_with(ctx, "main", True)

        comando = mock_dc.exec_cmd_stream.call_args[0][1]
        assert comando[comando.index("-u") + 1] == "mod_a,mod_b"
        assert comando[comando.index("--test-tags") + 1] == "/mod_a,/mod_b"
        assert result["modules"] == ["mod_a", "mod_b"]
        assert result["warnings"] == ["WARN de prueba"]
        assert result["total"] == 1

    def test_base_default_head(self, tmp_path) -> None:
        from odev.commands.test import _execute_test

        mock_dc = MagicMock()
        ctx = _make_contexto(tmp_path)
        p_docker, p_rutas, p_env, p_validar, p_sel = self._patches(tmp_path, mock_dc)
        with p_docker, p_rutas, p_env, p_validar, p_sel as mock_sel:
            _execute_test(ctx, changed=True)
            mock_sel.assert_called_once_with(ctx, None, False)

    def test_seleccion_vacia_no_lanza_odoo(self, tmp_path, capsys) -> None:
        from odev.commands.test import _execute_test

        mock_dc = MagicMock()
        ctx = _make_contexto(tmp_path)
        p_docker, p_rutas, p_env, p_validar, p_sel = self._patches(
            tmp_path, mock_dc, ([], ["submodulo git 'vendor/oca' cambiado"])
        )
        with p_docker, p_rutas, p_env, p_validar, p_sel:
            result = _execute_test(ctx, changed=True)

        mock_dc.exec_cmd_stream.assert_not_called()
        assert result["modules"] == []
        assert result["warnings"] == ["submodulo git 'vendor/oca' cambiado"]
        assert result["total"] == 0
        assert result["failures"] == []
        assert capsys.readouterr().out == ""

    def test_sin_changed_no_agrega_claves_nuevas(self, tmp_path) -> None:
        from odev.commands.test import _execute_test

        mock_dc = MagicMock()
        mock_dc.exec_cmd_stream.return_value = _make_popen_mock(_TEST_OUTPUT_OK)
        ctx = _make_contexto(tmp_path)
        p_docker, p_rutas, p_env, p_validar, p_sel = self._patches(tmp_path, mock_dc)
        with p_docker, p_rutas, p_env, p_validar, p_sel as mock_sel:
            result = _execute_test(ctx, "my_module")
            mock_sel.assert_not_called()

        assert "modules" not in result
        assert "warnings" not in result

    def test_combinaciones_invalidas_levantan_value_error(self, tmp_path) -> None:
        import pytest

        from odev.commands.test import _execute_test

        ctx = _make_contexto(tmp_path)
        with pytest.raises(ValueError, match="--changed"):
            _execute_test(ctx)
        with pytest.raises(ValueError, match="excluyentes"):
            _execute_test(ctx, "my_module", changed=True)
        with pytest.raises(ValueError, match="--base"):
            _execute_test(ctx, "my_module", base="main")

    def test_fallo_de_docker_en_dependientes_es_runtime_error(self, tmp_path) -> None:
        """Contrato documentado: una consulta de dependientes fallida es RuntimeError.

        Un CalledProcessError de docker no escapa crudo: se envuelve con el
        mismo contexto que el RuntimeError de psql, encadenado con 'from'.
        """
        import subprocess

        import pytest

        from odev.commands.test import _execute_test
        from odev.core.changed_modules import DeteccionCambios, ModuloDetectado

        ctx = _make_contexto(tmp_path)
        deteccion = DeteccionCambios(modulos=[ModuloDetectado("mod_a", tmp_path / "mod_a")])
        fallo = subprocess.CalledProcessError(1, ["docker", "compose", "exec"])
        with (
            patch("odev.commands.test.detectar_modulos_cambiados", return_value=deteccion),
            patch("odev.commands.test.listar_modulos_disponibles", return_value=set()),
            patch("odev.commands.test._execute_sql", side_effect=fallo),
        ):
            with pytest.raises(RuntimeError, match="--with-dependents no pudo consultar") as exc:
                _execute_test(ctx, changed=True, with_dependents=True)

        assert exc.value.__cause__ is fallo
