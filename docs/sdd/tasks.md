# SDD Task Breakdown: odev CLI Usability and Configuration Improvements

- **Date**: 2026-03-25
- **Status**: Draft
- **Spec**: [spec.md](./spec.md)
- **Design**: [design.md](./design.md)
- **Proposal**: [proposal.md](./proposal.md)
- **Total tasks**: 16
- **Estimated effort**: ~2.5 days

---

## Batch 1 — Quick Wins (~0.5 day)

No dependencies between tasks. All can be committed independently.

---

### Task T-01: Enterprise addons_path ordering fix
- **Improvement**: P7
- **Batch**: 1
- **Effort**: S (<1hr)
- **Dependencies**: none
- **Files to modify**: `src/odev/templates/project/odoo.conf.j2`, `tests/test_config.py`
- **Files to create**: none

#### What to do
1. Open `src/odev/templates/project/odoo.conf.j2`.
2. Find the two `addons_path` lines (one in the `{% if addon_container_paths is defined %}` branch, one in the `{% else %}` fallback).
3. In both branches, move the enterprise path from AFTER the addon paths to BEFORE them:
   - **With addon_container_paths**: Change to `addons_path = {% if enterprise_enabled %}/mnt/enterprise-addons,{% endif %}{{ addon_container_paths | join(',') }}`
   - **Fallback**: Change to `addons_path = {% if enterprise_enabled %}/mnt/enterprise-addons,{% endif %}/mnt/extra-addons`
4. Update the existing test `test_addons_path_con_enterprise` in `tests/test_config.py` to assert the new ordering: `assert "addons_path = /mnt/enterprise-addons,/mnt/extra-addons" in contenido` (enterprise FIRST).
5. Run `pytest tests/test_config.py -v` to verify.

#### Acceptance criteria
- AC-P7-01: With `enterprise_enabled=True`, generated `odoo.conf` has `/mnt/enterprise-addons` as the FIRST entry in `addons_path`.
- AC-P7-02: With `enterprise_enabled=False`, generated `odoo.conf` has no `/mnt/enterprise-addons`.
- AC-P7-03: With `enterprise_enabled=True` and no `addon_container_paths`, the fallback path is `/mnt/enterprise-addons,/mnt/extra-addons`.

#### Test tasks
- Update `test_addons_path_con_enterprise` in `tests/test_config.py` to assert enterprise path comes first.
- Add `test_addons_path_sin_enterprise` if not already present, asserting no enterprise path in output.
- Add `test_addons_path_enterprise_fallback` for the case without `addon_container_paths`.

---

### Task T-02: Add `--yes` flag to `load-backup`
- **Improvement**: P5
- **Batch**: 1
- **Effort**: S (<1hr)
- **Dependencies**: none
- **Files to modify**: `src/odev/commands/load_backup.py`
- **Files to create**: none

#### What to do
1. Open `src/odev/commands/load_backup.py`.
2. Add a `yes` parameter to the `load_backup()` function signature:
   ```python
   yes: bool = typer.Option(
       False,
       "--yes", "-y",
       help="Skip confirmation prompt (for automation/CI).",
   ),
   ```
3. Find the `typer.confirm("Continuar?", default=False)` call (~line 89).
4. Replace the confirmation block with:
   ```python
   warning(f"Esto REEMPLAZARA la base de datos '{nombre_bd}' con el contenido del backup!")
   if not yes and not typer.confirm("Continuar?", default=False):
       info("Operacion cancelada.")
       raise typer.Exit()
   ```
5. Verify the warning message is still printed even when `--yes` is passed (only the interactive prompt is skipped).

#### Acceptance criteria
- AC-P5-01: `odev load-backup backup.zip --yes` completes without interactive prompts.
- AC-P5-02: `odev load-backup backup.zip -y` (short form) also works.
- AC-P5-04: Without `--yes`, interactive confirmation works exactly as before.
- AC-P5-05: The warning message is displayed even when `--yes` is used.

#### Test tasks
- Add test in `tests/test_load_backup.py` (or inline in existing test file) verifying the `yes` parameter is accepted by the function signature.
- Test that confirmation is skipped when `yes=True`.

---

### Task T-03: Add `--yes` flag to `reset-db`
- **Improvement**: P5
- **Batch**: 1
- **Effort**: S (<1hr)
- **Dependencies**: none
- **Files to modify**: `src/odev/commands/reset_db.py`
- **Files to create**: none

#### What to do
1. Open `src/odev/commands/reset_db.py`.
2. Add a `yes` parameter to the `reset_db()` function signature:
   ```python
   yes: bool = typer.Option(
       False,
       "--yes", "-y",
       help="Skip confirmation prompt (for automation/CI).",
   ),
   ```
3. Find the `typer.confirm("Estas seguro?", default=False)` call (~line 40).
4. Replace with:
   ```python
   warning("Esto ELIMINARA la base de datos y TODOS los datos!")
   if not yes:
       confirmacion = typer.confirm("Estas seguro?", default=False)
       if not confirmacion:
           info("Operacion cancelada.")
           raise typer.Exit()
   ```

#### Acceptance criteria
- AC-P5-03: `odev reset-db --yes` completes without interactive prompts.
- AC-P5-04: Without `--yes`, interactive confirmation works exactly as before.

#### Test tasks
- Add test in `tests/test_reset_db.py` (or existing test file) verifying the `yes` parameter is accepted.

---

### Task T-04: Add `is_service_running()` to `DockerCompose`
- **Improvement**: P4
- **Batch**: 1
- **Effort**: S (<1hr)
- **Dependencies**: none
- **Files to modify**: `src/odev/core/docker.py`, `tests/test_docker.py`
- **Files to create**: none

#### What to do
1. Open `src/odev/core/docker.py`.
2. Add a new method `is_service_running()` to the `DockerCompose` class, after the `ps_parsed()` method:
   ```python
   def is_service_running(self, service: str) -> bool:
       """Check if a specific service has a running container."""
       servicios = self.ps_parsed()
       for svc in servicios:
           if svc.get("Service") == service and svc.get("State") == "running":
               return True
       return False
   ```
3. Write unit tests in `tests/test_docker.py` for the new method.

#### Acceptance criteria
- The method returns `True` when the service has `State == "running"` in `ps_parsed()` output.
- The method returns `False` when the service is in any other state (`exited`, `created`, `restarting`).
- The method returns `False` when `ps_parsed()` returns an empty list.
- The method returns `False` when the service name is not found in the output.

#### Test tasks
- Add `TestIsServiceRunning` class in `tests/test_docker.py` with:
  - `test_returns_true_when_running`: Mock `ps_parsed` to return `[{"Service": "db", "State": "running"}]`, assert `True`.
  - `test_returns_false_when_not_running`: Mock with `State: "exited"`, assert `False`.
  - `test_returns_false_when_service_absent`: Mock with empty list, assert `False`.

---

### Task T-05: Add pre-flight check to `load-backup`
- **Improvement**: P4
- **Batch**: 1
- **Effort**: S (<1hr)
- **Dependencies**: T-04 (`is_service_running` must exist)
- **Files to modify**: `src/odev/commands/load_backup.py`
- **Files to create**: none

#### What to do
1. Open `src/odev/commands/load_backup.py`.
2. Locate the `DockerCompose` instantiation (`dc = obtener_docker(contexto)`, ~line 59).
3. Insert the pre-flight check AFTER the `dc` instantiation and BEFORE the zip validation (`if not zipfile.is_zipfile(backup):`):
   ```python
   # Pre-flight: verify db container is running
   if not dc.is_service_running("db"):
       error(
           "El servicio de base de datos no esta corriendo. "
           "Ejecuta 'odev up' primero."
       )
       raise typer.Exit(1)
   ```
4. Ensure `error` is imported from `odev.core.console` (it likely already is).
5. The check must appear BEFORE both the confirmation prompt and the zip validation, so the user gets immediate feedback.

#### Acceptance criteria
- AC-P4-01: Running `odev load-backup` with containers stopped prints error and exits with code 1.
- AC-P4-02: Running `odev load-backup` with containers running proceeds normally.
- AC-P4-03: The error appears before any confirmation prompt.
- AC-P4-04: The error appears before the backup zip is opened or validated.

#### Test tasks
- Add test verifying that when `is_service_running("db")` returns `False`, the command exits with code 1 and prints the appropriate error message (mock `obtener_docker` and `is_service_running`).

---

### Task T-06: Nested schema validation for `odev.yaml`
- **Improvement**: P8
- **Batch**: 1
- **Effort**: M (1-3hr)
- **Dependencies**: none
- **Files to modify**: `src/odev/core/project.py`, `tests/test_project.py`
- **Files to create**: none

#### What to do
1. Open `src/odev/core/project.py`.
2. Add the `_ESQUEMA_NESTED` constant after the existing `_ESQUEMA_ODEV_YAML` dict (~line 64):
   ```python
   _ESQUEMA_NESTED: dict[str, dict[str, type | tuple[type, ...]]] = {
       "odoo": {"version": str, "image": str},
       "database": {"image": str},
       "enterprise": {"enabled": bool, "path": str},
       "services": {"pgweb": bool},
       "paths": {
           "addons": (list, str),
           "config": str, "snapshots": str, "logs": str, "docs": str,
       },
       "project": {"name": str, "description": str, "working_dir": str},
       "sdd": {"enabled": bool, "language": str},
   }
   ```
3. Enhance the `_validar_esquema()` function (lines 67-100) by adding a third pass after the existing two passes:
   - For each section in `_ESQUEMA_NESTED`: if the section exists in `datos` and is a `dict`, iterate its keys.
   - Unknown nested keys: append warning `"Clave desconocida '{key}' en seccion '{section}' de {ruta_archivo}. Posible error tipografico."`
   - Type mismatches: check `isinstance(value, expected_type)`. For tuple types (e.g., `(list, str)`), check against the tuple. Append warning with the expected vs actual type.
4. All new checks produce warnings only, never errors. The project continues to load normally.
5. Write tests in `tests/test_project.py`.

#### Acceptance criteria
- AC-P8-01: `enterprise.enbled: true` (typo) produces warning about unknown key `enbled` in section `enterprise`.
- AC-P8-02: `enterprise.enabled: "yes"` produces warning about expected `bool`, got `str`.
- AC-P8-03: `paths.addons: 42` (int) produces warning about expected `list` or `str`, got `int`.
- AC-P8-04: A fully valid `odev.yaml` produces zero warnings.
- AC-P8-05: Unknown top-level keys still produce warnings (existing behavior preserved).
- AC-P8-06: The project loads and operates normally even when warnings are emitted.

#### Test tasks
- Add `TestValidarEsquemaNested` class in `tests/test_project.py` with:
  - `test_typo_in_nested_key_produces_warning`: Create config with `enterprise.enbled`, verify warning.
  - `test_wrong_type_in_nested_value_produces_warning`: Create config with `enterprise.enabled: "yes"`, verify warning mentions `bool`.
  - `test_valid_nested_config_no_warnings`: Create valid config, patch `warning`, assert not called.
  - `test_paths_addons_accepts_list_and_string`: Verify no warning for both `list` and `str` values.
  - `test_none_value_produces_warning`: Verify `enterprise.path: null` produces type warning.

---

## Batch 2 — Config Lifecycle (~1 day)

Tasks have dependencies: T-07 and T-08 must precede T-09, T-10, T-11.

---

### Task T-07: Add `ruta_enterprise` property to `ProjectConfig`
- **Improvement**: P1 (prerequisite)
- **Batch**: 2
- **Effort**: S (<1hr)
- **Dependencies**: none
- **Files to modify**: `src/odev/core/project.py`
- **Files to create**: none

#### What to do
1. Open `src/odev/core/project.py`.
2. Locate the `enterprise_habilitado` property (~line 162).
3. Add a new property immediately after it:
   ```python
   @property
   def ruta_enterprise(self) -> str:
       """Path to enterprise addons directory."""
       return self.datos.get("enterprise", {}).get("path", "./enterprise")
   ```
4. This property is needed by `core/regen.py` to resolve the enterprise path from `odev.yaml`.

#### Acceptance criteria
- `ProjectConfig.ruta_enterprise` returns the value from `enterprise.path` in `odev.yaml`.
- When `enterprise.path` is not set, it defaults to `"./enterprise"`.

#### Test tasks
- Add test in `tests/test_project.py`:
  - `test_ruta_enterprise_from_config`: Create config with `enterprise.path: "/shared/enterprise"`, assert property returns it.
  - `test_ruta_enterprise_default`: Create config without `enterprise.path`, assert default `"./enterprise"`.

---

### Task T-08: Create `core/regen.py` — shared regeneration engine
- **Improvement**: P1
- **Batch**: 2
- **Effort**: L (3-8hr)
- **Dependencies**: T-07 (`ruta_enterprise` property)
- **Files to modify**: none
- **Files to create**: `src/odev/core/regen.py`, `tests/test_regen.py`

#### What to do
1. Create `src/odev/core/regen.py` with the following public API:
   - `RegenResult` dataclass with fields: `archivos_regenerados: list[Path]`, `archivos_sin_cambios: list[Path]`, `advertencias: list[str]`.
   - `construir_contexto_templates(config, env_values, directorio_config, directorio_trabajo=None) -> dict[str, Any]`: Build the unified template context merging `odev.yaml` structural values with `.env` runtime values. Use `env_or(key, default)` pattern for runtime values. Include both UPPERCASE keys (for env/odoo.conf templates) and snake_case keys (for docker-compose template). See design doc section 2.2 for the complete key mapping.
   - `regenerar_configuracion(contexto, include_env=False) -> RegenResult`: Load `ProjectConfig`, load `.env`, call `construir_contexto_templates()`, render `docker-compose.yml` from `docker-compose.yml.j2`, render `odoo.conf` via `generate_odoo_conf()`, optionally render `.env` via `write_env()`. Track which files changed by comparing content before/after.
   - `necesita_regeneracion(contexto) -> bool`: Compare mtime of `.odev.yaml` against `docker-compose.yml` and `config/odoo.conf`. Return `True` if yaml is newer or generated files are missing. Return `False` if no yaml exists.
   - `_renderizar_template(nombre_template, destino, valores)`: Internal helper using Jinja2 `Environment` with `FileSystemLoader` pointing to `get_project_templates_dir()`.
   - `_extraer_tag_db(imagen_db) -> str`: Extract PostgreSQL version tag from image string (e.g., `"pgvector/pgvector:pg16"` -> `"16"`).
   - `_extraer_env_values(valores) -> dict[str, str]`: Extract UPPERCASE env keys from the merged context dict.
2. Import dependencies: `construir_addon_mounts`, `generate_odoo_conf`, `load_env`, `write_env` from `core/config.py`; `ProjectConfig` from `core/project.py`; `ProjectContext` from `core/resolver.py`.
3. Create `tests/test_regen.py` with the `proyecto_con_config` fixture and test classes as specified in design doc section 12.1.

#### Acceptance criteria
- `construir_contexto_templates()` preserves `.env` runtime values (ports, passwords) while taking structural values from `odev.yaml`.
- `regenerar_configuracion()` produces a valid `docker-compose.yml` and `odoo.conf` from templates.
- `.env` is NOT touched when `include_env=False`.
- `.env` IS regenerated when `include_env=True`.
- `necesita_regeneracion()` returns `True` when `.odev.yaml` mtime > generated file mtime.
- `necesita_regeneracion()` returns `False` when generated files are newer.
- `necesita_regeneracion()` returns `True` when a generated file is missing.
- `necesita_regeneracion()` returns `False` when `.odev.yaml` does not exist.

#### Test tasks
Create `tests/test_regen.py` with:
- `TestConstruirContextoTemplates`:
  - `test_preserva_env_runtime_values`
  - `test_structural_from_odev_yaml`
  - `test_defaults_when_env_empty`
  - `test_addon_mounts_built_from_config`
  - `test_enterprise_flag_propagated`
- `TestNecesitaRegeneracion`:
  - `test_yaml_newer_triggers_regen`
  - `test_no_regen_when_files_newer`
  - `test_missing_generated_file_triggers_regen`
  - `test_no_yaml_no_regen`
- `TestRegenerarConfiguracion`:
  - `test_regenera_compose_y_odoo_conf`
  - `test_preserva_env_por_defecto`
  - `test_include_env_regenera_env`

---

### Task T-09: Create `commands/reconfigure.py` and register in `main.py`
- **Improvement**: P1
- **Batch**: 2
- **Effort**: M (1-3hr)
- **Dependencies**: T-08 (`core/regen.py` must exist)
- **Files to modify**: `src/odev/main.py`
- **Files to create**: `src/odev/commands/reconfigure.py`, `tests/test_reconfigure.py`

#### What to do
1. Create `src/odev/commands/reconfigure.py` with the `reconfigure()` function:
   - Parameters: `include_env: bool = typer.Option(False, "--include-env", ...)` and `dry_run: bool = typer.Option(False, "--dry-run", ...)`.
   - Resolve project context via `requerir_proyecto(obtener_nombre_proyecto())`.
   - If `--dry-run`: call `necesita_regeneracion()` and print whether regeneration is needed, then return without writing.
   - Otherwise: call `regenerar_configuracion(contexto, include_env=include_env)`.
   - Print summary of regenerated files. Print advertencias as warnings.
   - Print hint: `"Run 'odev restart' to apply changes to running containers."` if files were regenerated.
2. Register in `src/odev/main.py`:
   - Add import: `from odev.commands.reconfigure import reconfigure`
   - Add registration: `app.command(name="reconfigure")(reconfigure)` (place near existing command registrations, follow the existing pattern with try/except ImportError if that pattern is used).
3. Create `tests/test_reconfigure.py` with basic tests.

#### Acceptance criteria
- AC-P1-01: After editing `enterprise.enabled: true`, running `odev reconfigure` produces a `docker-compose.yml` with enterprise volume mount.
- AC-P1-02: After `odev reconfigure`, `.env` has the same `DB_PASSWORD` as before.
- AC-P1-03: After adding an addon path, `odev reconfigure` updates both `docker-compose.yml` and `odoo.conf`.
- AC-P1-04: `odev reconfigure --dry-run` writes zero files to disk.
- AC-P1-05: `odev reconfigure --include-env` regenerates `.env` preserving runtime values.
- AC-P1-06: The command works in both inline and external project modes.

#### Test tasks
Create `tests/test_reconfigure.py` with:
- `test_dry_run_no_file_changes`: Verify `--dry-run` does not modify any files.
- `test_reconfigure_updates_compose`: Verify docker-compose.yml is regenerated.
- `test_reconfigure_preserves_env`: Verify `.env` is untouched by default.

---

### Task T-10: Auto-regen on `odev up`
- **Improvement**: P3
- **Batch**: 2
- **Effort**: M (1-3hr)
- **Dependencies**: T-08 (`core/regen.py` with `necesita_regeneracion` and `regenerar_configuracion`)
- **Files to modify**: `src/odev/commands/up.py`
- **Files to create**: none

#### What to do
1. Open `src/odev/commands/up.py`.
2. Add import for `warning` from `odev.core.console` (if not already imported).
3. Add imports: `from odev.core.regen import necesita_regeneracion, regenerar_configuracion`.
4. Replace the current auto-regen block (the `.env` vs `odoo.conf` mtime check, ~lines 66-77) with the expanded version from design doc section 4.1:
   - First check: if `necesita_regeneracion(contexto)` is `True`, print warning `"odev.yaml changed since last generation. Regenerating configs..."`, call `regenerar_configuracion(contexto)`, and print names of regenerated files.
   - Else block: preserve the existing `.env`-only mtime check as a fallback for when `odev.yaml` has not changed but `.env` was modified.
5. The existing logic for `_asegurar_directorio_logs`, starting containers, and printing URLs remains unchanged.

#### Acceptance criteria
- AC-P3-01: Editing `odev.yaml` and running `odev up` triggers automatic regeneration with a warning.
- AC-P3-02: Running `odev up` when `odev.yaml` has not changed produces no regeneration and no warning.
- AC-P3-03: The mtime comparison works for external projects (`~/.odev/projects/<name>/`).
- AC-P3-04: If `docker-compose.yml` or `odoo.conf` is manually deleted, `odev up` regenerates them.
- AC-P3-05: The existing `.env` -> `odoo.conf` mtime check still works independently.

#### Test tasks
- Tests for the mtime-based triggering are covered by `tests/test_regen.py` (T-08). Integration testing of the `up` command with auto-regen can be added if the project has a test harness for command invocation. At minimum, verify that the import of `necesita_regeneracion` and `regenerar_configuracion` does not break the `up` command.

---

### Task T-11: Add `--force` flag to `adopt`
- **Improvement**: P6
- **Batch**: 2
- **Effort**: M (1-3hr)
- **Dependencies**: none (soft dependency on T-08 for regen logic, but `--force` works without it by re-running the full adopt flow)
- **Files to modify**: `src/odev/commands/adopt.py`
- **Files to create**: none

#### What to do
1. Open `src/odev/commands/adopt.py`.
2. Add `force` parameter to the `adopt()` function signature:
   ```python
   force: bool = typer.Option(
       False,
       "--force", "-f",
       help="Force re-adopt: remove existing registry entry and regenerate config.",
   ),
   ```
3. Modify the `.odev.yaml` existence check (~lines 79-84):
   ```python
   if (ruta / ".odev.yaml").exists() and not force:
       error(
           f"'{ruta}' ya es un proyecto odev (tiene .odev.yaml). "
           "Usa 'odev up' directamente o --force para re-adoptar."
       )
       raise typer.Exit(1)
   ```
4. Modify the registry existence check (~lines 127-130):
   ```python
   existente = registro.obtener(name)
   if existente:
       if force:
           import shutil
           warning(f"Removing existing project '{name}' from registry...")
           registro.eliminar(name)
           if existente.directorio_config.exists():
               shutil.rmtree(existente.directorio_config)
           info(f"Cleaned up: {existente.directorio_config}")
       else:
           error(
               f"Ya existe un proyecto '{name}' en el registro. "
               "Usa --force para re-adoptar."
           )
           raise typer.Exit(1)
   ```
5. Ensure `warning` is imported from `odev.core.console`.
6. Safety: `--force` NEVER deletes the working directory. Only the config directory under `~/.odev/projects/<name>/` and the registry entry.

#### Acceptance criteria
- AC-P6-01: `odev adopt --force` on an already-adopted project succeeds.
- AC-P6-02: After `odev adopt --force`, the registry entry points to the new config directory.
- AC-P6-03: After `odev adopt --force`, generated files reflect the current layout detection.
- AC-P6-04: Without `--force`, the existing error message includes a hint about `--force`.
- AC-P6-05: `odev adopt --force` on a project with `.odev.yaml` in the working directory succeeds.
- AC-P6-06: The working directory is never deleted by `--force`.

#### Test tasks
- Add tests verifying:
  - `--force` parameter is accepted in the function signature.
  - When `force=True` and project exists in registry, the entry is removed before re-adoption.
  - When `force=False` and project exists, the error message mentions `--force`.

---

## Batch 3 — Enterprise (~1 day)

---

### Task T-12: Add `ENTERPRISE_DIR` constant to `registry.py`
- **Improvement**: P2 (prerequisite)
- **Batch**: 3
- **Effort**: S (<1hr)
- **Dependencies**: none
- **Files to modify**: `src/odev/core/registry.py`
- **Files to create**: none

#### What to do
1. Open `src/odev/core/registry.py`.
2. Locate the `ODEV_HOME` constant (~line 26).
3. Add after it:
   ```python
   ENTERPRISE_DIR = ODEV_HOME / "enterprise"  # ~/.odev/enterprise/
   ```
4. This constant is used by `commands/enterprise.py` and `commands/adopt.py` to locate the shared enterprise storage.

#### Acceptance criteria
- `ENTERPRISE_DIR` resolves to `~/.odev/enterprise/`.
- The constant is importable: `from odev.core.registry import ENTERPRISE_DIR`.

#### Test tasks
- Add a trivial import test or verify in existing registry tests that `ENTERPRISE_DIR` is a `Path` ending with `enterprise`.

---

### Task T-13: Create `commands/enterprise.py` — `import` and `path` subcommands
- **Improvement**: P2
- **Batch**: 3
- **Effort**: M (1-3hr)
- **Dependencies**: T-12 (`ENTERPRISE_DIR` constant)
- **Files to modify**: `src/odev/main.py`
- **Files to create**: `src/odev/commands/enterprise.py`, `tests/test_enterprise_cmd.py`

#### What to do
1. Create `src/odev/commands/enterprise.py` with a `typer.Typer` app:
   ```python
   app = typer.Typer(name="enterprise", help="Manage shared Odoo Enterprise addons.", no_args_is_help=True)
   ```
2. Implement helper functions:
   - `_version_dir(version: str) -> Path`: Returns `ENTERPRISE_DIR / version`.
   - `_contar_modulos(directorio: Path) -> int`: Counts subdirectories containing `__manifest__.py`.
3. Implement `enterprise_import` command (`@app.command(name="import")`):
   - Parameters: `version: str`, `path: Path` (exists=True, file_okay=False), `copy: bool` (default False), `force: bool` (default False).
   - If `destino` exists and not `force`: error and exit.
   - If `destino` exists and `force`: remove (unlink if symlink, `shutil.rmtree` if dir).
   - Create `ENTERPRISE_DIR` if needed (`mkdir(parents=True, exist_ok=True)`).
   - Count modules in source. Warn if 0.
   - If `copy`: `shutil.copytree(source, destino)`. Else: `destino.symlink_to(source.resolve())`.
   - Print success with module count.
4. Implement `enterprise_path` command (`@app.command(name="path")`):
   - Parameter: `version: str`.
   - If `destino` does not exist: exit with code 1.
   - Else: `typer.echo(str(destino.resolve()))` (raw path for scripting, no Rich formatting).
5. Register in `src/odev/main.py`:
   ```python
   try:
       from odev.commands.enterprise import app as enterprise_app
       app.add_typer(enterprise_app, name="enterprise")
   except ImportError:
       pass
   ```
6. Create `tests/test_enterprise_cmd.py` with initial tests.

#### Acceptance criteria
- AC-P2-01: `odev enterprise import 19.0 /path/to/enterprise` creates a symlink at `~/.odev/enterprise/19.0`.
- AC-P2-02: `odev enterprise import 19.0 /path --copy` creates a real directory with module files.
- AC-P2-06: `odev enterprise path 19.0` prints the path to stdout with no extra output.

#### Test tasks
Create `tests/test_enterprise_cmd.py` with:
- `test_contar_modulos`: Verify correct count with fake modules.
- `test_contar_modulos_dir_vacio`: Returns 0.
- `test_contar_modulos_dir_inexistente`: Returns 0.
- `test_import_creates_symlink`: Test the import logic creates a symlink.
- `test_import_copy_creates_directory`: Test `--copy` mode.
- `test_import_force_overwrites`: Test `--force` overwrites existing.

---

### Task T-14: Add `status` and `link` subcommands to `enterprise.py`
- **Improvement**: P2
- **Batch**: 3
- **Effort**: M (1-3hr)
- **Dependencies**: T-13 (enterprise module must exist), T-08 (`core/regen.py` for link's regeneration trigger)
- **Files to modify**: `src/odev/commands/enterprise.py`
- **Files to create**: none

#### What to do
1. Implement `enterprise_status` command (`@app.command(name="status")`):
   - If `ENTERPRISE_DIR` does not exist: print info message and return.
   - Create a `rich.table.Table` with columns: Version, Modules, Path, Type.
   - Iterate `ENTERPRISE_DIR` entries. For each dir/symlink: count modules, determine type (`"symlink"` or `"copy"`), resolve real path.
   - Print the table.
   - After the table, iterate registered projects via `Registry().listar()`. For each, load `ProjectConfig` and print whether enterprise is enabled and its path.
2. Implement `enterprise_link` command (`@app.command(name="link")`):
   - Parameter: `version: str = typer.Option(None, "--version", ...)`.
   - Resolve project context via `requerir_proyecto(obtener_nombre_proyecto())`.
   - If `version` is None, use `contexto.config.version_odoo`.
   - Check that `_version_dir(version)` exists; error if not.
   - Load `.odev.yaml` with `yaml.safe_load`, update `enterprise.enabled = True` and `enterprise.path` to the resolved shared path.
   - Write back with `yaml.dump(datos, ..., sort_keys=False)`.
   - Call `regenerar_configuracion(contexto)` from `core/regen.py` to propagate the change.
   - Print summary of changes.

#### Acceptance criteria
- AC-P2-03: `odev enterprise link` updates `odev.yaml` with `enterprise.enabled: true` and the correct path.
- AC-P2-04: After `odev enterprise link`, running `odev up` starts containers with enterprise mounted.
- AC-P2-05: `odev enterprise status` lists all available versions with module counts.

#### Test tasks
- `test_status_empty`: Verify output when no enterprise versions exist.
- `test_link_updates_yaml`: Mock project context, verify `odev.yaml` is updated correctly.

---

### Task T-15: Integrate shared enterprise detection in `adopt`
- **Improvement**: P2
- **Batch**: 3
- **Effort**: M (1-3hr)
- **Dependencies**: T-12 (`ENTERPRISE_DIR` constant), T-13 (enterprise module for consistency)
- **Files to modify**: `src/odev/commands/adopt.py`
- **Files to create**: none

#### What to do
1. Open `src/odev/commands/adopt.py`.
2. Locate the enterprise path determination in `_construir_valores()` (~line 258) or the section where `layout.tiene_enterprise` is evaluated.
3. Add a check for shared enterprise when local enterprise is not detected:
   ```python
   if not layout.tiene_enterprise:
       from odev.core.registry import ENTERPRISE_DIR
       shared_enterprise = ENTERPRISE_DIR / odoo_version
       if shared_enterprise.exists():
           if not no_interactive:
               usar_shared = questionary.confirm(
                   f"Shared enterprise addons found for {odoo_version}. Use them?",
                   default=True,
               ).ask()
               if usar_shared:
                   enterprise_path = str(shared_enterprise.resolve())
                   layout.tiene_enterprise = True
           else:
               enterprise_path = str(shared_enterprise.resolve())
               layout.tiene_enterprise = True
               info(f"Using shared enterprise addons: {shared_enterprise}")
   ```
4. Ensure the resolved `enterprise_path` is passed correctly into the template values and written to `odev.yaml`.
5. The exact placement depends on the current code structure -- the check should happen between layout detection and the call to `_construir_valores()`, or within `_construir_valores()` itself.

#### Acceptance criteria
- AC-P2-07: `odev adopt` on a project without local enterprise offers to use shared enterprise when available.
- In `--no-interactive` mode, shared enterprise is auto-used if available.
- If no shared enterprise exists, the adopt flow continues as before (no change).

#### Test tasks
- Add test verifying that when `ENTERPRISE_DIR / version` exists and `layout.tiene_enterprise` is False, the shared enterprise path is used.
- Add test verifying that when no shared enterprise exists, the original behavior is preserved.

---

### Task T-16: Integrate shared enterprise detection in `init`
- **Improvement**: P2
- **Batch**: 3
- **Effort**: S (<1hr)
- **Dependencies**: T-12 (`ENTERPRISE_DIR` constant)
- **Files to modify**: `src/odev/commands/init.py`
- **Files to create**: none

#### What to do
1. Open `src/odev/commands/init.py`.
2. Locate the enterprise wizard step in `_wizard_interactivo()` (~line 196) where the user is asked "Habilitar enterprise addons?".
3. When the user answers yes, add a check for shared enterprise:
   ```python
   from odev.core.registry import ENTERPRISE_DIR
   shared_enterprise = ENTERPRISE_DIR / odoo_version
   if shared_enterprise.exists():
       usar_shared = questionary.confirm(
           f"Shared enterprise addons found for {odoo_version}. Use shared location?",
           default=True,
       ).ask()
       if usar_shared:
           enterprise_path = str(shared_enterprise.resolve())
       else:
           enterprise_path = "./enterprise"
   else:
       enterprise_path = "./enterprise"
   ```
4. Ensure `enterprise_path` is propagated to the template values.

#### Acceptance criteria
- FR-P2-009: During `odev init`, when the user enables enterprise and a shared version exists, the wizard offers to use it.
- If no shared enterprise exists, the wizard continues as before with `./enterprise`.

#### Test tasks
- Verify that the import of `ENTERPRISE_DIR` does not break the init command.
- Integration test: when shared enterprise exists and user says yes, the generated `odev.yaml` has the shared path.

---

## Summary

| Task | Improvement | Batch | Effort | Dependencies |
|------|-------------|-------|--------|-------------|
| T-01 | P7 (enterprise ordering) | 1 | S | none |
| T-02 | P5 (`--yes` load-backup) | 1 | S | none |
| T-03 | P5 (`--yes` reset-db) | 1 | S | none |
| T-04 | P4 (`is_service_running`) | 1 | S | none |
| T-05 | P4 (pre-flight check) | 1 | S | T-04 |
| T-06 | P8 (nested schema) | 1 | M | none |
| T-07 | P1 (`ruta_enterprise` property) | 2 | S | none |
| T-08 | P1 (`core/regen.py`) | 2 | L | T-07 |
| T-09 | P1 (`reconfigure` command) | 2 | M | T-08 |
| T-10 | P3 (auto-regen on `up`) | 2 | M | T-08 |
| T-11 | P6 (`adopt --force`) | 2 | M | none |
| T-12 | P2 (`ENTERPRISE_DIR`) | 3 | S | none |
| T-13 | P2 (`import` + `path` cmds) | 3 | M | T-12 |
| T-14 | P2 (`status` + `link` cmds) | 3 | M | T-13, T-08 |
| T-15 | P2 (adopt integration) | 3 | M | T-12 |
| T-16 | P2 (init integration) | 3 | S | T-12 |

### Commit Strategy

| Commit | Tasks | Description |
|--------|-------|-------------|
| 1 | T-01, T-02, T-03 | `[IMP] P7+P5: enterprise ordering fix + --yes flag` |
| 2 | T-04, T-05 | `[IMP] P4: pre-flight checks for load-backup` |
| 3 | T-06 | `[IMP] P8: nested schema validation for odev.yaml` |
| 4 | T-07, T-08 | `[ADD] P1: core/regen.py shared regeneration engine` |
| 5 | T-09 | `[ADD] P1: odev reconfigure command` |
| 6 | T-10 | `[IMP] P3: auto-regen on odev up when odev.yaml changes` |
| 7 | T-11 | `[IMP] P6: adopt --force flag for re-adoption` |
| 8 | T-12, T-13 | `[ADD] P2: odev enterprise import/path subcommands` |
| 9 | T-14 | `[ADD] P2: odev enterprise status/link subcommands` |
| 10 | T-15, T-16 | `[IMP] P2: shared enterprise integration in adopt/init` |

### Dependency Graph

```
Batch 1 (all independent):
  T-01 (P7)
  T-02 (P5)
  T-03 (P5)
  T-04 (P4) --> T-05 (P4)
  T-06 (P8)

Batch 2:
  T-07 --> T-08 --> T-09 (P1 chain)
                --> T-10 (P3)
  T-11 (P6, independent)

Batch 3:
  T-12 --> T-13 --> T-14 (P2 enterprise chain)
       --> T-15 (P2 adopt)
       --> T-16 (P2 init)
  T-08 ------> T-14 (link needs regen engine)
```
