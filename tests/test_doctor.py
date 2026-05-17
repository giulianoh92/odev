"""Tests para odev.commands.doctor — diagnostico del entorno.

Verifica las funciones de verificacion individuales del comando doctor,
mockeando subprocess y socket para evitar dependencias externas.
Cubre 0.4.0: MAILHOG_PORT en puertos_a_verificar, simbolo puerto_disponible
importado desde odev.core.ports, backfill de entradas legacy y GC de puertos.
"""

import socket
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from odev.commands.doctor import (
    _verificar_docker,
    _verificar_docker_compose,
    _verificar_python,
)


class TestVerificarDocker:
    """Grupo de tests para la verificacion de Docker."""

    def test_docker_disponible(self):
        """Retorna CheckResult ok cuando Docker esta instalado y responde."""
        with (
            patch("shutil.which", return_value="/usr/bin/docker"),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="Docker version 24.0.7, build afdd53b",
            )

            resultado = _verificar_docker()

        assert isinstance(resultado, dict)
        assert resultado["status"] == "ok"

    def test_docker_no_instalado(self):
        """Retorna CheckResult fail cuando Docker no esta instalado."""
        with patch("shutil.which", return_value=None):
            resultado = _verificar_docker()

        assert isinstance(resultado, dict)
        assert resultado["status"] == "fail"

    def test_docker_instalado_pero_no_responde(self):
        """Retorna CheckResult fail cuando Docker esta instalado pero no responde."""
        with (
            patch("shutil.which", return_value="/usr/bin/docker"),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(returncode=1, stdout="")

            resultado = _verificar_docker()

        assert isinstance(resultado, dict)
        assert resultado["status"] == "fail"

    def test_docker_timeout(self):
        """Retorna CheckResult fail cuando Docker tarda demasiado en responder."""
        import subprocess

        with (
            patch("shutil.which", return_value="/usr/bin/docker"),
            patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="docker", timeout=10)),
        ):
            resultado = _verificar_docker()

        assert isinstance(resultado, dict)
        assert resultado["status"] == "fail"


class TestVerificarDockerCompose:
    """Grupo de tests para la verificacion de Docker Compose v2."""

    def test_compose_v2_disponible(self):
        """Retorna CheckResult ok cuando Docker Compose v2 esta disponible."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="Docker Compose version v2.21.0",
            )

            resultado = _verificar_docker_compose()

        assert isinstance(resultado, dict)
        assert resultado["status"] == "ok"

    def test_compose_v2_no_disponible(self):
        """Retorna CheckResult fail cuando Docker Compose v2 no esta disponible."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="")

            resultado = _verificar_docker_compose()

        assert isinstance(resultado, dict)
        assert resultado["status"] == "fail"

    def test_compose_file_not_found(self):
        """Retorna CheckResult fail cuando docker no esta en el PATH."""
        with patch("subprocess.run", side_effect=FileNotFoundError):
            resultado = _verificar_docker_compose()

        assert isinstance(resultado, dict)
        assert resultado["status"] == "fail"


class TestVerificarPython:
    """Grupo de tests para la verificacion de Python."""

    def test_python_version_adecuada(self):
        """Retorna CheckResult ok con Python 3.10+."""
        with (
            patch("platform.python_version", return_value="3.12.0"),
            patch("odev.commands.doctor.sys") as mock_sys,
        ):
            mock_sys.version_info = (3, 12, 0)

            resultado = _verificar_python()

        assert isinstance(resultado, dict)
        assert resultado["status"] == "ok"

    def test_python_version_antigua(self):
        """Retorna CheckResult fail con Python menor a 3.10."""
        with (
            patch("platform.python_version", return_value="3.8.10"),
            patch("odev.commands.doctor.sys") as mock_sys,
        ):
            mock_sys.version_info = (3, 8, 10)

            resultado = _verificar_python()

        assert isinstance(resultado, dict)
        assert resultado["status"] == "fail"


class TestPuertoDisponibleDoctor:
    """Grupo de tests para la funcion puerto_disponible importada desde core.ports."""

    def test_puerto_libre(self):
        """Retorna True para un puerto libre."""
        from odev.core.ports import puerto_disponible

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            puerto_libre = s.getsockname()[1]

        assert puerto_disponible(puerto_libre) is True

    def test_puerto_ocupado(self):
        """Retorna False para un puerto ocupado."""
        from odev.core.ports import puerto_disponible

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("127.0.0.1", 0))
            puerto_ocupado = s.getsockname()[1]

            assert puerto_disponible(puerto_ocupado) is False


# ── T17 RED: Tests de MAILHOG, canonicalizacion de puerto_disponible, backfill y GC ──


@pytest.fixture
def registry_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Fixture de registro aislado para tests de doctor."""
    import odev.core.registry as reg_mod

    monkeypatch.setattr(reg_mod, "ODEV_HOME", tmp_path)
    monkeypatch.setattr(reg_mod, "REGISTRY_PATH", tmp_path / "registry.yaml")
    monkeypatch.setattr(reg_mod, "PROJECTS_DIR", tmp_path / "projects")
    (tmp_path / "projects").mkdir()
    from odev.core.registry import Registry

    return Registry()


class TestVerificarPuertosMailhog:
    """Verifica que MAILHOG_PORT se incluye en la verificacion de puertos."""

    def test_verificar_puertos_includes_mailhog(self, tmp_path: Path, monkeypatch) -> None:
        """_verificar_puertos verifica MAILHOG_PORT del .env.

        REQ-DC-1: MAILHOG_PORT debe aparecer en la lista de verificacion.
        """
        from odev.commands.doctor import _verificar_puertos
        from odev.core.compat import ProjectMode

        # Setup: proyecto con .env que incluye MAILHOG_PORT
        env_file = tmp_path / ".env"
        env_file.write_text(
            "WEB_PORT=8069\nDB_PORT=5432\nPGWEB_PORT=8081\n"
            "DEBUGPY_PORT=5678\nMAILHOG_PORT=8025\n"
        )

        with (
            patch("odev.commands.doctor.detect_mode", return_value=(ProjectMode.PROJECT, tmp_path)),
            patch("odev.commands.doctor.puerto_disponible", return_value=True),
        ):
            resultado = _verificar_puertos()

        # Debe retornar CheckResult ok (todos disponibles) sin crashear por MAILHOG_PORT
        assert isinstance(resultado, dict)
        assert resultado["status"] == "ok"

    def test_verificar_puertos_uses_canonical_puerto_disponible(
        self, tmp_path: Path
    ) -> None:
        """doctor usa odev.core.ports.puerto_disponible, no el simbolo local eliminado.

        REQ-DC-2: el modulo doctor no debe tener _puerto_disponible local.
        """
        import odev.commands.doctor as doctor_mod

        assert not hasattr(doctor_mod, "_puerto_disponible"), (
            "doctor.py no debe tener _puerto_disponible local — "
            "debe importar de odev.core.ports"
        )

    def test_verificar_puertos_mailhog_conflict_reported(
        self, tmp_path: Path
    ) -> None:
        """Cuando MAILHOG_PORT esta ocupado, doctor reporta el conflicto.

        REQ-DC-1 Scenario: MAILHOG conflict detected.
        """
        from odev.commands.doctor import _verificar_puertos
        from odev.core.compat import ProjectMode

        env_file = tmp_path / ".env"
        env_file.write_text("MAILHOG_PORT=8025\n")

        def mock_puerto_disponible(puerto: int) -> bool:
            return puerto != 8025  # MAILHOG_PORT ocupado

        with (
            patch("odev.commands.doctor.detect_mode", return_value=(ProjectMode.PROJECT, tmp_path)),
            patch("odev.commands.doctor.puerto_disponible", side_effect=mock_puerto_disponible),
        ):
            resultado = _verificar_puertos()

        assert isinstance(resultado, dict)
        assert resultado["status"] == "fail"


class TestDoctorBackfill:
    """Verifica el backfill de entradas legacy desde .env."""

    def test_doctor_backfills_legacy_entry_from_env(
        self, tmp_path: Path, registry_tmp, monkeypatch
    ) -> None:
        """doctor rellena el campo ports en entradas legacy con .env completo.

        REQ-PA-3: backfill de 5 claves de puertos desde .env.
        """

        # Crear proyecto legacy (sin campo ports)
        work_dir = tmp_path / "mi-proyecto"
        work_dir.mkdir()
        env_file = work_dir / ".env"
        env_file.write_text(
            "WEB_PORT=8069\nDB_PORT=5432\nPGWEB_PORT=8081\n"
            "DEBUGPY_PORT=5678\nMAILHOG_PORT=8025\n"
        )

        from odev.core.registry import RegistryEntry

        entry_legacy = RegistryEntry(
            nombre="mi-proyecto",
            directorio_trabajo=work_dir,
            directorio_config=work_dir,
            modo="inline",
            version_odoo="18.0",
            fecha_creacion="2026-01-01",
            ports=None,  # legacy
        )
        registry_tmp.registrar(entry_legacy)

        # Ejecutar backfill
        from odev.commands.doctor import _verificar_registry_puertos

        _verificar_registry_puertos(registry_tmp)

        # Verificar que los ports fueron backfilleados
        actualizado = registry_tmp.obtener("mi-proyecto")
        assert actualizado is not None
        assert actualizado.ports is not None
        assert actualizado.ports["WEB_PORT"] == 8069
        assert actualizado.ports["MAILHOG_PORT"] == 8025

    def test_doctor_backfill_partial_env_warns(
        self, tmp_path: Path, registry_tmp, monkeypatch, capsys
    ) -> None:
        """Con .env parcial, backfill llena solo las claves presentes y emite warning.

        REQ-PA-3 Scenario: partial .env — missing MAILHOG_PORT.
        """
        work_dir = tmp_path / "proyecto-parcial"
        work_dir.mkdir()
        env_file = work_dir / ".env"
        # Sin MAILHOG_PORT
        env_file.write_text("WEB_PORT=8069\nDB_PORT=5432\n")

        from odev.core.registry import RegistryEntry

        entry = RegistryEntry(
            nombre="proyecto-parcial",
            directorio_trabajo=work_dir,
            directorio_config=work_dir,
            modo="inline",
            version_odoo="18.0",
            fecha_creacion="2026-01-01",
            ports=None,
        )
        registry_tmp.registrar(entry)

        from odev.commands.doctor import _verificar_registry_puertos

        _verificar_registry_puertos(registry_tmp)

        actualizado = registry_tmp.obtener("proyecto-parcial")
        assert actualizado is not None
        assert actualizado.ports is not None
        assert "WEB_PORT" in actualizado.ports
        assert "DB_PORT" in actualizado.ports
        # MAILHOG_PORT no debe aparecer (no estaba en .env)
        assert "MAILHOG_PORT" not in (actualizado.ports or {})

    def test_doctor_gc_removes_stale_entry(
        self, tmp_path: Path, registry_tmp
    ) -> None:
        """GC de doctor elimina entradas cuyo directorio ya no existe.

        REQ-PA-4: limpiar_obsoletos libera puertos de entradas stale.
        """
        stale_dir = tmp_path / "stale-project"
        # No crear el directorio — simula proyecto eliminado

        from odev.core.registry import RegistryEntry

        entry = RegistryEntry(
            nombre="stale-project",
            directorio_trabajo=stale_dir,
            directorio_config=stale_dir,
            modo="inline",
            version_odoo="18.0",
            fecha_creacion="2026-01-01",
            ports={"WEB_PORT": 8069},
        )
        registry_tmp.registrar(entry)

        # Verificar que los puertos estan reclamados antes del GC
        assert 8069 in registry_tmp.puertos_ocupados()

        # Ejecutar GC (via limpiar_obsoletos que ya hace esto)
        eliminados = registry_tmp.limpiar_obsoletos()

        assert "stale-project" in eliminados
        assert 8069 not in registry_tmp.puertos_ocupados()


# ── TestDoctorJsonOutput (C1: doctor --json) ──────────────────────────────────


def _doctor_json_patches(tmp_path, overrides: dict | None = None):
    """Build the standard list of patches for doctor --json tests.

    All _verificar_* functions and detect_mode are replaced with safe mocks
    that return ok/info CheckResult dicts. Pass overrides to replace specific
    function mocks.
    """
    from unittest.mock import patch

    from odev.core.compat import ProjectMode

    ok = {"name": "x", "status": "ok", "message": "ok", "hint": None}
    gc = {
        "name": "registry-gc",
        "status": "info",
        "message": "GC removed 0 orphans; backfilled 0 entries",
        "hint": None,
    }
    overrides = overrides or {}

    return [
        patch(
            "odev.commands.doctor._verificar_docker",
            return_value=overrides.get("_verificar_docker", ok),
        ),
        patch(
            "odev.commands.doctor._verificar_docker_compose",
            return_value=overrides.get("_verificar_docker_compose", ok),
        ),
        patch(
            "odev.commands.doctor._verificar_python",
            return_value=overrides.get("_verificar_python", ok),
        ),
        patch(
            "odev.commands.doctor._verificar_proyecto",
            return_value=overrides.get("_verificar_proyecto", ok),
        ),
        patch(
            "odev.commands.doctor._verificar_env",
            return_value=overrides.get("_verificar_env", ok),
        ),
        patch(
            "odev.commands.doctor._ejecutar_registry_gc_y_backfill",
            return_value=overrides.get("_ejecutar_registry_gc_y_backfill", gc),
        ),
        patch(
            "odev.commands.doctor._verificar_puertos",
            return_value=overrides.get("_verificar_puertos", ok),
        ),
        patch(
            "odev.commands.doctor._verificar_docker_compose_file",
            return_value=overrides.get("_verificar_docker_compose_file", ok),
        ),
        patch(
            "odev.commands.doctor._verificar_odoo_conf",
            return_value=overrides.get("_verificar_odoo_conf", ok),
        ),
        patch(
            "odev.commands.doctor._verificar_addons",
            return_value=overrides.get("_verificar_addons", ok),
        ),
        patch(
            "odev.commands.doctor._verificar_version_compatible",
            return_value=overrides.get("_verificar_version_compatible", ok),
        ),
        patch(
            "odev.commands.doctor.detect_mode",
            return_value=overrides.get(
                "detect_mode", (ProjectMode.PROJECT, tmp_path)
            ),
        ),
    ]


def _run_doctor(patches_to_apply, json_output: bool = True):
    """Run doctor() with a list of patches, return (stdout, stderr, exit_code)."""
    import io
    from unittest.mock import patch

    import typer

    from odev.commands.doctor import doctor

    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    exit_code = 0

    with patch("sys.stdout", stdout_buf), patch("sys.stderr", stderr_buf):
        for p in patches_to_apply:
            p.start()
        try:
            doctor(json_output=json_output)
        except (SystemExit, typer.Exit) as e:
            exit_code = e.code if isinstance(e, SystemExit) else e.exit_code
        finally:
            for p in patches_to_apply:
                p.stop()

    return stdout_buf.getvalue(), stderr_buf.getvalue(), exit_code


class TestDoctorJsonOutput:
    """Tests for C1: doctor --json JSON output path.

    All 7 scenarios from spec C1-S1 through C1-S7.
    """

    def test_c1_s1_all_pass_schema(self, tmp_path):
        """C1-S1: all checks ok → valid JSON, summary.fail==0, exit 0."""
        import json

        patches = _doctor_json_patches(tmp_path)
        out, _, exit_code = _run_doctor(patches, json_output=True)

        assert out.strip(), f"stdout should not be empty, got: {out!r}"
        data = json.loads(out.strip())
        assert "checks" in data
        assert "summary" in data
        assert "version" in data
        assert "exit_code" in data
        assert data["summary"]["fail"] == 0
        assert exit_code == 0

    def test_c1_s2_one_fail_exit_1(self, tmp_path):
        """C1-S2: one fail-level check → summary.fail >= 1, exit 1."""
        import json

        fail_result = {
            "name": "docker",
            "status": "fail",
            "message": "Docker not running",
            "hint": "Start Docker",
        }
        patches = _doctor_json_patches(tmp_path, overrides={"_verificar_docker": fail_result})
        out, _, exit_code = _run_doctor(patches, json_output=True)

        data = json.loads(out.strip())
        assert data["summary"]["fail"] >= 1
        assert exit_code == 1

    def test_c1_s4_default_rich_path_untouched(self, tmp_path):
        """C1-S4: without --json, Rich output printed (no JSON on stdout)."""
        import json as _json
        from unittest.mock import patch

        from odev.core.compat import ProjectMode

        detect_patch = patch(
            "odev.commands.doctor.detect_mode",
            return_value=(ProjectMode.NONE, None),
        )
        out, _, _ = _run_doctor([detect_patch], json_output=False)

        # In Rich mode, stdout should NOT contain a JSON document
        try:
            _json.loads(out.strip())
            is_json = True
        except (ValueError, _json.JSONDecodeError):
            is_json = False
        assert not is_json, f"Rich mode should not emit JSON to stdout, got: {out!r}"

    def test_c1_s5_json_suppresses_rich(self, tmp_path):
        """C1-S5: --json suppresses Rich decorations from stdout."""
        import json

        patches = _doctor_json_patches(tmp_path)
        out, _, _ = _run_doctor(patches, json_output=True)

        # Should not contain Rich markup like [OK], [WARN], [FAIL]
        assert "[OK]" not in out, f"Rich output should not appear in JSON mode: {out!r}"
        assert "[FAIL]" not in out, f"Rich output should not appear in JSON mode: {out!r}"
        # Should be valid JSON
        data = json.loads(out.strip())
        assert "checks" in data

    def test_c1_s6_hint_non_null(self, tmp_path):
        """C1-S6: check with hint → hint field is non-null string."""
        import json

        hint_result = {
            "name": "docker",
            "status": "fail",
            "message": "Docker not running",
            "hint": "Run: sudo systemctl start docker",
        }
        patches = _doctor_json_patches(tmp_path, overrides={"_verificar_docker": hint_result})
        out, _, _ = _run_doctor(patches, json_output=True)

        data = json.loads(out.strip())
        docker_check = next(c for c in data["checks"] if c["name"] == "docker")
        assert docker_check["hint"] is not None
        assert isinstance(docker_check["hint"], str)
        assert len(docker_check["hint"]) > 0

    def test_c1_s7_warn_exit_0(self, tmp_path):
        """C1-S7: warn-level check → summary.warn >= 1, exit 0 (warn != fail)."""
        import json

        warn_result = {
            "name": "version",
            "status": "warn",
            "message": "version behind",
            "hint": None,
        }
        patches = _doctor_json_patches(
            tmp_path, overrides={"_verificar_version_compatible": warn_result}
        )
        out, _, exit_code = _run_doctor(patches, json_output=True)

        data = json.loads(out.strip())
        assert data["summary"]["warn"] >= 1
        assert exit_code == 0

    def test_c1_s3_no_project_stderr_json(self, tmp_path):
        """C1-S3 (W1 fix): no project context -> stderr JSON error, stdout empty, exit 1.

        Per spec: GIVEN no odev project is initialized, WHEN doctor --json,
        THEN stderr contains {"error": "<message>"}, stdout is empty, exit 1.
        """
        import json

        from odev.core.compat import ProjectMode

        patches = _doctor_json_patches(
            tmp_path,
            overrides={"detect_mode": (ProjectMode.NONE, None)},
        )
        out, err, exit_code = _run_doctor(patches, json_output=True)

        # W1: stdout must be empty when no project found
        assert out.strip() == "", f"stdout must be empty with no project, got: {out!r}"
        # W1: stderr must contain JSON with error key
        assert err.strip(), "stderr must contain error JSON when no project found"
        err_data = json.loads(err.strip())
        assert "error" in err_data, f"stderr JSON must have 'error' key, got: {err_data}"
        # W1: exit code must be 1
        assert exit_code == 1, f"exit code must be 1 when no project, got: {exit_code}"

    def test_c1_s5_no_rich_leak_in_json_mode(self, tmp_path):
        """C1-S5 / W2: --json mode must NOT emit Rich text to stdout.

        Verifies that _verificar_registry_puertos does NOT call _imprimir_warn
        (which calls console.print) when doctor is in JSON mode.
        All _verificar_* are fully mocked so only doctor() itself can emit.
        """
        import json

        patches = _doctor_json_patches(tmp_path)
        out, _, _ = _run_doctor(patches, json_output=True)

        # stdout must contain ONLY valid JSON (no Rich markup leakage)
        lines = [ln for ln in out.splitlines() if ln.strip()]
        assert len(lines) == 1, (
            f"stdout must contain exactly 1 line in JSON mode (got {len(lines)}): {out!r}"
        )
        data = json.loads(lines[0])
        assert "checks" in data
