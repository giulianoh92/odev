# SDD Proposal: odev CLI Usability and Configuration Improvements

- **Date**: 2026-03-25
- **Status**: Draft
- **Author**: Auto-generated from real-world usage analysis
- **Scope**: 8 improvements across config management, enterprise workflow, UX, and validation
- **Branch**: TBD (suggest `feature/config-improvements`)

---

## 1. Executive Summary

This proposal addresses 8 interconnected improvements to the odev CLI, identified during real-world usage of the `adopt` workflow with the VitalCare ERP project (an Odoo.sh multi-company codebase with enterprise addons, multiple submodule addon paths, and automated agent workflows).

The central theme is **configuration lifecycle management**: odev currently treats project configuration as a one-shot generation event (at `init` or `adopt` time), but real projects require iterative configuration changes post-setup. Editing `odev.yaml` after initial generation has no effect on the runtime artifacts (`docker-compose.yml`, `odoo.conf`, `.env`), creating a frustrating gap between declared intent and actual behavior.

The 8 improvements form a cohesive change set that transforms `odev.yaml` from a static snapshot into a live source of truth, adds shared enterprise addon management, hardens destructive commands for automation, and adds schema enforcement to catch misconfigurations early.

**Net effect**: After this change set, a developer can edit `odev.yaml`, run `odev up`, and have all generated configs automatically reflect the new state -- with enterprise addons shared across projects, backup loading protected by pre-flight checks, and all commands usable in non-interactive CI/agent contexts.

---

## 2. Motivation

### Real-World Pain Points

During the adoption of the VitalCare ERP project (Odoo.sh layout, 757 enterprise modules, 15+ submodule addon paths), the following friction points were encountered in a single session:

1. **Config drift after adopt**: After running `odev adopt`, the generated `odev.yaml` correctly listed enterprise and addon paths. But editing `odev.yaml` to fix `enterprise.enabled: true` (which had been set to `false` due to a detection issue) had zero effect -- `docker-compose.yml` and `odoo.conf` still reflected the old values. There was no command to regenerate them.

2. **Enterprise disk waste**: Each project copies the full enterprise addon set (~500MB). With 3 projects targeting Odoo 19.0, that is 1.5GB of identical files with no sharing mechanism.

3. **Re-adopt failure**: Running `odev adopt` again to "fix" the config failed with `"Ya existe un proyecto 'vitalcare-erp' en el registro."` (line 129 of `adopt.py`). The only recovery path was manually deleting the registry entry and config directory.

4. **Backup loading crash**: Running `odev load-backup backup.zip` before `odev up` produced a raw `CalledProcessError` traceback from `psql` because the db container was not running. No pre-flight check exists.

5. **Agent workflow blocked**: An AI agent running `odev load-backup` could not proceed because `typer.confirm("Continuar?", default=False)` on line 89 of `load_backup.py` requires interactive input with no `--yes` bypass.

6. **Enterprise addons_path ordering**: The `odoo.conf.j2` template (line 3) appends `/mnt/enterprise-addons` AFTER the extra-addons paths. Enterprise modules must be FIRST to correctly override Community Edition modules (e.g., `web_enterprise` must override `web`).

7. **Silent config errors**: Setting `enterprise.enabled: true` in `odev.yaml` produced no warning, no error, and no effect. The `_validar_esquema()` function in `project.py` only checks top-level key types, not nested field values or semantic validity.

---

## 3. Scope

### 3.1 All Improvements at a Glance

| ID | Title | Priority | Effort | New Files | Modified Files |
|----|-------|----------|--------|-----------|----------------|
| P1 | Config Regeneration Command (`reconfigure`) | HIGH | Medium | `commands/reconfigure.py` | `main.py` |
| P2 | Shared Enterprise Addons (`~/.odev/enterprise/`) | HIGH | Large | `commands/enterprise.py` | `main.py`, `commands/adopt.py`, `commands/init.py`, `registry.py` |
| P3 | odev.yaml as Source of Truth (auto-regen on `up`) | HIGH | Small | None | `commands/up.py` |
| P4 | `load-backup` Pre-flight Checks | MEDIUM | Small | None | `commands/load_backup.py`, `core/docker.py` |
| P5 | `load-backup --yes` Flag | MEDIUM | Trivial | None | `commands/load_backup.py` |
| P6 | `adopt --force` Flag | MEDIUM | Small | None | `commands/adopt.py` |
| P7 | Enterprise addons_path Ordering | LOW | Trivial | None | `templates/project/odoo.conf.j2` |
| P8 | odev.yaml Schema Enforcement | LOW | Medium | None | `core/project.py` |

### 3.2 Detailed Specifications

---

#### P1 — Config Regeneration Command (`odev reconfigure`)

**Problem**: After `odev adopt` or `odev init`, if you edit `odev.yaml`, changes to `enterprise.enabled`, `paths.addons`, `odoo.version`, etc. do not propagate to the generated files (`docker-compose.yml`, `.env`, `odoo.conf`). There is no command to trigger regeneration.

**Solution**: New `odev reconfigure` command.

**Behavior**:
1. Resolve the current project context via `requerir_proyecto()`.
2. Load `odev.yaml` via `ProjectConfig`.
3. Load the existing `.env` file to preserve user-edited values (DB credentials, ports, etc.).
4. Merge `odev.yaml` values with `.env` values (odev.yaml wins for structural settings like addon paths and enterprise; `.env` wins for runtime values like passwords and ports).
5. Re-render `docker-compose.yml` from `docker-compose.yml.j2` with merged values.
6. Re-render `odoo.conf` from `odoo.conf.j2` with merged values.
7. Optionally re-render `.env` if `--env` flag is passed (default: preserve existing `.env`).
8. Print diff summary of what changed.

**New file**: `src/odev/commands/reconfigure.py`

**Key implementation details**:

```
# The merge strategy for .env preservation:
# 1. Read existing .env via load_env()
# 2. Read odev.yaml via ProjectConfig
# 3. Structural values from odev.yaml override:
#    - ODOO_IMAGE (from odoo.image)
#    - DB_IMAGE (from database.image)
#    - COMPOSE_PROJECT_NAME (from project.name)
# 4. Runtime values from .env are preserved:
#    - DB_USER, DB_PASSWORD, DB_NAME, WEB_PORT, etc.
# 5. Addon mounts rebuilt from odev.yaml paths.addons
# 6. Enterprise toggle from odev.yaml enterprise.enabled
```

**Registration in main.py**:
```python
from odev.commands.reconfigure import reconfigure
app.command(name="reconfigure")(reconfigure)
```

**Effort estimate**: ~150 lines of new code. The template rendering infrastructure already exists in `_wizards.py::renderizar_templates()` and `config.py::generate_odoo_conf()`. The main work is building the merge logic between `.env` values and `odev.yaml` values.

---

#### P2 — Shared Enterprise Addons

**Problem**: Enterprise addons are ~500MB per version. Each project copies them independently. No standard location, no sharing, no version management.

**Solution**: Global enterprise addon storage at `~/.odev/enterprise/{version}/` with a new `odev enterprise` subcommand group.

**New subcommands**:

| Command | Description |
|---------|-------------|
| `odev enterprise import <version> <path>` | Copy or symlink enterprise addons to `~/.odev/enterprise/<version>/` |
| `odev enterprise link [--version]` | Link current project to shared enterprise for its Odoo version |
| `odev enterprise status` | Show available enterprise versions and which projects use them |
| `odev enterprise path <version>` | Print the path to shared enterprise for a given version (for scripting) |

**New file**: `src/odev/commands/enterprise.py`

**Integration with adopt/init**:
- In `commands/adopt.py::_construir_valores()` (line 226): When `layout.tiene_enterprise` is False, check if `~/.odev/enterprise/{version}/` exists. If it does, ask "Use shared enterprise addons?" (interactive) or auto-use (non-interactive).
- In `commands/init.py::_wizard_interactivo()` (line 196): When user answers "Habilitar enterprise addons?" with yes, check for shared enterprise. If found, offer to use it instead of creating a local `./enterprise` directory.

**odev.yaml support**:
- `enterprise.path` already supports arbitrary paths. Shared enterprise would set it to `~/.odev/enterprise/19.0` (absolute path).
- No schema changes needed -- just conventions.

**New constant in registry.py**:
```python
ENTERPRISE_DIR = ODEV_HOME / "enterprise"  # ~/.odev/enterprise/
```

**Effort estimate**: ~250 lines of new code. The `import` subcommand needs careful handling of symlinks vs copies (prefer symlinks with a `--copy` flag for portability). The `link` subcommand is a thin wrapper that edits `odev.yaml` and triggers regeneration (delegates to P1).

---

#### P3 — odev.yaml as Source of Truth (auto-regen on `up`)

**Problem**: `odev up` currently only checks if `.env` is newer than `odoo.conf` to trigger regeneration (line 71 of `up.py`). Edits to `odev.yaml` are completely ignored after initial generation.

**Solution**: Extend the mtime check in `up.py` to also compare `odev.yaml` against `docker-compose.yml` and `odoo.conf`. If `odev.yaml` is newer, regenerate both before starting containers.

**Modified file**: `src/odev/commands/up.py`

**Current auto-regen logic** (lines 66-77):
```python
# Auto-regenerar odoo.conf si el .env es mas reciente
archivo_odoo_conf = rutas.config_dir / "odoo.conf"
if not archivo_odoo_conf.exists() or rutas.env_file.stat().st_mtime > archivo_odoo_conf.stat().st_mtime:
    generate_odoo_conf(...)
    info("Se regenero config/odoo.conf desde .env")
```

**Proposed extended logic**:
```python
# Detect if odev.yaml changed since last generation
odev_yaml_path = rutas.odev_config  # .odev.yaml or odev.yaml in config dir
docker_compose_path = rutas.docker_compose_file

needs_regen = False

if odev_yaml_path.exists():
    yaml_mtime = odev_yaml_path.stat().st_mtime

    if docker_compose_path.exists() and yaml_mtime > docker_compose_path.stat().st_mtime:
        needs_regen = True
    if archivo_odoo_conf.exists() and yaml_mtime > archivo_odoo_conf.stat().st_mtime:
        needs_regen = True

if needs_regen:
    warning("odev.yaml has changed since last generation. Regenerating configs...")
    # Delegate to reconfigure logic (shared with P1)
    _regenerar_configs(contexto, rutas)
```

**Important nuance for EXTERNAL mode**: In external mode (`adopt`), the `odev.yaml` lives in `~/.odev/projects/<name>/odev.yaml`, not in the working directory. The `ProjectPaths.odev_config` property already points to the correct location (`self._root / ".odev.yaml"` on line 141 of `paths.py`). For external projects, `self._root` is the config directory, so this resolves correctly to `~/.odev/projects/<name>/.odev.yaml`.

**Effort estimate**: ~40 lines of modified code. The regeneration logic itself is shared with P1 (extract a `_regenerar_configs()` helper into `_helpers.py` or a new `core/regen.py`).

---

#### P4 — `load-backup` Pre-flight Checks

**Problem**: `load-backup` (line 59 of `load_backup.py`) creates a `DockerCompose` instance and immediately starts executing `exec_cmd` on the `db` service without verifying it is running. If containers are down, the user sees a raw `subprocess.CalledProcessError` traceback.

**Solution**: Add a pre-flight check before the confirmation prompt (fail fast).

**Modified files**: `src/odev/commands/load_backup.py`, `src/odev/core/docker.py`

**New helper in docker.py**:
```python
def is_service_running(self, service: str) -> bool:
    """Check if a specific service has a running container.

    Uses `docker compose ps --format json` and checks for the service
    in the parsed output with State == "running".
    """
    servicios = self.ps_parsed()
    for svc in servicios:
        if svc.get("Service") == service and svc.get("State") == "running":
            return True
    return False
```

**Pre-flight in load_backup.py** (insert after line 59, before line 62):
```python
# Pre-flight: verify db container is running
if not dc.is_service_running("db"):
    error(
        "El servicio de base de datos no esta corriendo. "
        "Ejecuta 'odev up' primero."
    )
    raise typer.Exit(1)
```

**Placement**: The check must go BEFORE the confirmation prompt (line 88) so the user is not asked to confirm an operation that will fail.

**Effort estimate**: ~20 lines total (helper + check). The `ps_parsed()` method already exists and returns structured JSON data.

---

#### P5 — `load-backup --yes` Flag

**Problem**: `load-backup` uses `typer.confirm()` (line 89) with no bypass mechanism. This blocks automation (CI pipelines, AI agents, scripted workflows).

**Solution**: Add `--yes` / `-y` flag to skip the confirmation prompt.

**Modified file**: `src/odev/commands/load_backup.py`

**Change to function signature** (line 26):
```python
def load_backup(
    backup: Path = typer.Argument(...),
    neutralize: bool = typer.Option(True, ...),
    yes: bool = typer.Option(
        False,
        "--yes", "-y",
        help="Skip confirmation prompt (for automation).",
    ),
) -> None:
```

**Change to confirmation logic** (replace lines 88-91):
```python
warning(f"Esto REEMPLAZARA la base de datos '{nombre_bd}' con el contenido del backup!")
if not yes and not typer.confirm("Continuar?", default=False):
    info("Operacion cancelada.")
    raise typer.Exit()
```

**Also apply to `reset-db`**: The `reset_db` command (line 40 of `reset_db.py`) has the same pattern with `typer.confirm()` and no `--yes` flag. Add the same flag for consistency.

**Effort estimate**: ~10 lines total across both files. Trivial change.

---

#### P6 — `adopt --force` Flag

**Problem**: `odev adopt` checks the registry (line 128 of `adopt.py`) and exits with error if a project with the same name already exists. There is no way to update or re-adopt. The check on line 79 also blocks if `.odev.yaml` exists in the target directory.

**Solution**: Add `--force` flag that removes the existing registry entry and config directory before re-adopting.

**Modified file**: `src/odev/commands/adopt.py`

**Change to function signature** (add parameter):
```python
def adopt(
    directorio: str = typer.Argument(...),
    name: str = typer.Option(None, ...),
    odoo_version: str = typer.Option(None, ...),
    no_interactive: bool = typer.Option(False, ...),
    force: bool = typer.Option(
        False,
        "--force", "-f",
        help="Force re-adopt: remove existing registry entry and regenerate config.",
    ),
) -> None:
```

**Change to .odev.yaml check** (lines 79-84):
```python
if (ruta / ".odev.yaml").exists() and not force:
    error(
        f"'{ruta}' ya es un proyecto odev (tiene .odev.yaml). "
        "Usa 'odev up' directamente o --force para re-adoptar."
    )
    raise typer.Exit(1)
```

**Change to registry check** (lines 127-130):
```python
existente = registro.obtener(name)
if existente:
    if force:
        warning(f"Eliminando proyecto existente '{name}' del registro...")
        registro.eliminar(name)
        # Clean up old config directory
        import shutil
        if existente.directorio_config.exists():
            shutil.rmtree(existente.directorio_config)
    else:
        error(f"Ya existe un proyecto '{name}' en el registro. Usa --force para re-adoptar.")
        raise typer.Exit(1)
```

**Alternative consideration**: Instead of full cleanup, `--force` could delegate to `odev reconfigure` (P1) when the project already exists. This would be a nicer UX: `odev adopt --force` detects existing project, re-runs detection, and regenerates configs without losing `.env` customizations. Implementation: check if project exists, if so, call the reconfigure logic with the newly detected layout. This creates a dependency on P1.

**Effort estimate**: ~30 lines of modified code for the basic version. ~50 lines if integrating with P1's reconfigure logic.

---

#### P7 — Enterprise addons_path Ordering

**Problem**: In `odoo.conf.j2` (line 3), enterprise addons are appended AFTER extra-addons:
```
addons_path = {{ addon_container_paths | join(',') }}{% if enterprise_enabled %},/mnt/enterprise-addons{% endif %}
```

Enterprise modules like `web_enterprise` MUST appear before their CE counterparts in `addons_path` for correct module resolution. Odoo uses the first matching module path.

**Solution**: Prepend enterprise path instead of appending.

**Modified file**: `src/odev/templates/project/odoo.conf.j2`

**Change line 3 from**:
```
addons_path = {{ addon_container_paths | join(',') }}{% if enterprise_enabled %},/mnt/enterprise-addons{% endif %}
```

**To**:
```
addons_path = {% if enterprise_enabled %}/mnt/enterprise-addons,{% endif %}{{ addon_container_paths | join(',') }}
```

**Also change line 5** (the fallback when `addon_container_paths` is not defined):
```
addons_path = {% if enterprise_enabled %}/mnt/enterprise-addons,{% endif %}/mnt/extra-addons
```

**Effort estimate**: 2 lines changed. Trivial, but high-impact for enterprise users.

---

#### P8 — odev.yaml Schema Enforcement

**Problem**: The current `_validar_esquema()` in `project.py` (lines 67-100) only validates:
- Unknown top-level keys (produces warnings)
- Type mismatch for top-level values (dict vs str, etc.)

It does NOT validate:
- Nested key names (e.g., `enterprise.enbled` typo goes unnoticed)
- Value types within nested dicts (e.g., `enterprise.enabled: "yes"` instead of `true`)
- Required fields
- Semantic constraints (e.g., `enterprise.path` must be a valid path-like string)

**Solution**: Enhance `_validar_esquema()` with nested schema validation. Two approaches:

**Approach A (recommended) -- Manual nested validation**:
Extend `_ESQUEMA_ODEV_YAML` with a nested schema dict and add recursive validation. This keeps the zero-dependency approach consistent with the current codebase (no pydantic/jsonschema added).

```python
_ESQUEMA_NESTED: dict[str, dict[str, type]] = {
    "odoo": {"version": str, "image": str},
    "database": {"image": str},
    "enterprise": {"enabled": bool, "path": str},
    "services": {"pgweb": bool},
    "paths": {"addons": (list, str), "config": str, "snapshots": str, "logs": str, "docs": str},
    "project": {"name": str, "description": str, "working_dir": str},
    "sdd": {"enabled": bool, "language": str},
}
```

**Approach B -- Pydantic models**:
Replace `ProjectConfig` with pydantic models for full validation. Adds a dependency but provides better error messages and IDE support. This is more appropriate for a future refactor.

**Modified file**: `src/odev/core/project.py`

**Behavior**:
- Unknown nested keys produce warnings (not errors) for forward compatibility.
- Type mismatches produce warnings (current behavior).
- Add a `--strict` flag to `odev doctor` that upgrades warnings to errors.

**Integration with existing validation** (line 129 of `project.py`):
The `_validar_esquema()` call already exists. The enhancement extends it without changing the call site.

**Effort estimate**: ~80 lines of new validation code. Testing effort is moderate (need parametrized tests for various invalid configs).

---

## 4. Dependencies

```
P7 (enterprise ordering)     -- no dependencies, standalone template fix
P5 (--yes flag)               -- no dependencies, standalone flag addition
P4 (pre-flight checks)        -- no dependencies, standalone guard
P8 (schema enforcement)       -- no dependencies, standalone validation

P1 (reconfigure command)      -- no dependencies, but is REQUIRED BY P3 and P6
P3 (auto-regen on up)         -- DEPENDS ON P1 (shares regeneration logic)
P6 (adopt --force)            -- SOFT DEPENDS ON P1 (can delegate to reconfigure)
P2 (shared enterprise)        -- SOFT DEPENDS ON P1 (link command triggers regen)
```

**Dependency graph**:

```
Independent:
  P4 (pre-flight)
  P5 (--yes flag)
  P7 (enterprise ordering)
  P8 (schema enforcement)

Chain:
  P1 (reconfigure) ──► P3 (auto-regen on up)
       │
       ├──► P6 (adopt --force, optional delegation)
       │
       └──► P2 (shared enterprise, link triggers regen)
```

---

## 5. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| **P1: .env merge loses user customizations** | Medium | High | Default behavior preserves ALL `.env` values; only `docker-compose.yml` and `odoo.conf` are regenerated from templates. Add `--include-env` flag to opt into `.env` regeneration. Always show diff of what changed. |
| **P1: Template values diverge between init/adopt/reconfigure** | Medium | Medium | Extract `_construir_valores()` into a shared module (`core/values.py`) used by all three commands. Current duplication between `init.py::_construir_valores()` and `adopt.py::_construir_valores()` is already a maintenance risk. |
| **P2: Symlinks break on different machines** | Low | Medium | Default to symlinks with `--copy` flag. Document that shared enterprise is per-machine. For CI/Docker, always use copy mode. |
| **P3: Auto-regen breaks running containers** | Medium | Medium | Only regenerate files, never automatically restart containers. Warn: "Configuration regenerated. Run `odev restart` to apply changes." The `odev up` command already does `docker compose up -d` which picks up compose file changes. |
| **P6: --force deletes user data** | Low | High | Only delete the `~/.odev/projects/<name>/` config directory, never the working directory. Always warn before deletion. Require explicit `--force`, never auto-clean. |
| **P7: Addon path order change breaks existing projects** | Low | Medium | This is a correctness fix. Enterprise MUST be first. Projects without enterprise are unaffected (the `{% if enterprise_enabled %}` guard remains). Projects with enterprise that relied on CE overriding EE had a bug, not a feature. |
| **P8: Stricter validation breaks existing configs** | Medium | Low | All new validations produce warnings, not errors. Errors only in `odev doctor --strict` mode. Forward-compatible: unknown nested keys are warned, not rejected. |

---

## 6. Success Criteria

### P1 — Config Regeneration Command
- [ ] `odev reconfigure` regenerates `docker-compose.yml` and `odoo.conf` from current `odev.yaml` values
- [ ] `.env` values (DB credentials, ports) are preserved unless `--include-env` is passed
- [ ] After editing `enterprise.enabled: true` in `odev.yaml`, running `odev reconfigure` produces a `docker-compose.yml` with the enterprise volume mount and an `odoo.conf` with `/mnt/enterprise-addons` in `addons_path`
- [ ] Adding a new addon path to `odev.yaml` `paths.addons` and running `odev reconfigure` updates both `docker-compose.yml` volumes/watch sections and `odoo.conf` addons_path

### P2 — Shared Enterprise Addons
- [ ] `odev enterprise import 19.0 /path/to/enterprise/` copies modules to `~/.odev/enterprise/19.0/`
- [ ] `odev enterprise status` shows available versions with module count
- [ ] `odev enterprise link` updates current project's `odev.yaml` `enterprise.path` to `~/.odev/enterprise/19.0` and sets `enterprise.enabled: true`
- [ ] After `odev enterprise link`, running `odev reconfigure` (or `odev up`) produces correct mounts
- [ ] `odev adopt` offers to use shared enterprise when available

### P3 — odev.yaml as Source of Truth
- [ ] Editing `odev.yaml` and running `odev up` triggers automatic regeneration with a warning message
- [ ] If `odev.yaml` is older than generated files, no regeneration occurs (no performance penalty)
- [ ] The mtime comparison works correctly for both inline and external project modes

### P4 — Pre-flight Checks
- [ ] Running `odev load-backup backup.zip` when containers are stopped shows: "El servicio de base de datos no esta corriendo. Ejecuta 'odev up' primero."
- [ ] The error appears BEFORE any confirmation prompt
- [ ] Running `odev load-backup backup.zip` when containers are running proceeds normally

### P5 — `--yes` Flag
- [ ] `odev load-backup backup.zip --yes` skips the confirmation prompt
- [ ] `odev load-backup backup.zip -y` (short form) also works
- [ ] `odev reset-db --yes` skips the confirmation prompt
- [ ] Without `--yes`, interactive confirmation works as before

### P6 — `adopt --force`
- [ ] `odev adopt --force` on an already-adopted project succeeds (re-detects layout, regenerates config)
- [ ] The old config directory is cleaned up before regeneration
- [ ] Without `--force`, the existing error message is shown with a hint to use `--force`
- [ ] `odev adopt --force` on a directory with `.odev.yaml` succeeds

### P7 — Enterprise addons_path Ordering
- [ ] Generated `odoo.conf` has `/mnt/enterprise-addons` BEFORE extra-addons paths when enterprise is enabled
- [ ] Generated `odoo.conf` has no enterprise path when enterprise is disabled
- [ ] Existing projects without enterprise are unaffected

### P8 — Schema Enforcement
- [ ] `enterprise.enbled: true` (typo) produces a warning: "Unknown key 'enbled' in section 'enterprise'"
- [ ] `enterprise.enabled: "yes"` (wrong type) produces a warning about expected bool
- [ ] `odev doctor` reports all schema warnings
- [ ] Unknown top-level keys still produce warnings (existing behavior preserved)
- [ ] Valid configs produce no warnings

---

## 7. Implementation Order

### Recommended Sequence

The implementation is organized into 3 batches, respecting dependencies and maximizing early value delivery.

#### Batch 1 — Quick Wins (no dependencies, immediate value)

| Order | ID | Effort | Why first |
|-------|----|--------|-----------|
| 1 | P7 | Trivial | 2-line template fix, correctness bug for all enterprise users |
| 2 | P5 | Trivial | 10-line flag addition, unblocks automation immediately |
| 3 | P4 | Small | 20-line guard, prevents confusing crash for common mistake |
| 4 | P8 | Medium | 80 lines, independent validation work, catches config errors early |

**Estimated effort**: 1 sprint (half-day)
**Commit strategy**: One commit for P7+P5+P4 (all trivial), one commit for P8

#### Batch 2 — Config Lifecycle (the core improvement chain)

| Order | ID | Effort | Why this order |
|-------|----|--------|----------------|
| 5 | P1 | Medium | Foundation for P3 and P6; the `reconfigure` command and its shared regeneration logic |
| 6 | P3 | Small | Extends P1's regen logic into `up` command; very high daily-use impact |
| 7 | P6 | Small | Extends `adopt` with `--force`, optionally delegates to P1 |

**Estimated effort**: 1 sprint (full day)
**Commit strategy**: One commit for P1, one commit for P3+P6

**Key architectural decision**: Extract regeneration logic into `src/odev/core/regen.py` (new module) shared by `reconfigure`, `up`, and `adopt --force`. This avoids duplicating the merge-and-regenerate logic across three commands.

Proposed `core/regen.py` public API:
```python
def regenerar_configs(
    contexto: ProjectContext,
    rutas: ProjectPaths,
    include_env: bool = False,
) -> list[str]:
    """Re-read odev.yaml + .env, re-render docker-compose.yml and odoo.conf.

    Returns list of files that were regenerated.
    """
```

#### Batch 3 — Enterprise Workflow

| Order | ID | Effort | Why last |
|-------|----|--------|----------|
| 8 | P2 | Large | Biggest change, benefits from P1 being done (link triggers regen) |

**Estimated effort**: 1 sprint (full day)
**Commit strategy**: One commit for the `enterprise` subcommand group, one commit for adopt/init integration

### Summary Timeline

```
Batch 1 (Quick Wins):     P7 → P5 → P4 → P8           ~0.5 day
Batch 2 (Config Lifecycle): P1 → P3 → P6               ~1 day
Batch 3 (Enterprise):      P2                           ~1 day
                                                        ─────────
                                                Total:  ~2.5 days
```

---

## Appendix A: File Impact Matrix

| File | P1 | P2 | P3 | P4 | P5 | P6 | P7 | P8 |
|------|----|----|----|----|----|----|----|----|
| `src/odev/main.py` | M | M | | | | | | |
| `src/odev/commands/reconfigure.py` | **N** | | | | | | | |
| `src/odev/commands/enterprise.py` | | **N** | | | | | | |
| `src/odev/commands/up.py` | | | M | | | | | |
| `src/odev/commands/load_backup.py` | | | | M | M | | | |
| `src/odev/commands/reset_db.py` | | | | | M | | | |
| `src/odev/commands/adopt.py` | | M | | | | M | | |
| `src/odev/commands/init.py` | | M | | | | | | |
| `src/odev/core/docker.py` | | | | M | | | | |
| `src/odev/core/project.py` | | | | | | | | M |
| `src/odev/core/regen.py` | **N** | | M | | | M | | |
| `src/odev/core/registry.py` | | M | | | | | | |
| `src/odev/templates/project/odoo.conf.j2` | | | | | | | M | |

**Legend**: **N** = New file, M = Modified

## Appendix B: Relation to Existing IMPROVEMENT-PLAN.md

The existing `docs/IMPROVEMENT-PLAN.md` tracked a code review improvement plan (security, stability, maintainability, enhancements) that is now 100% complete. This proposal is a **new, separate improvement effort** focused on usability and configuration lifecycle, identified from real-world usage rather than code review.

The only overlap is item **E2** (Schema validation for `.odev.yaml`) from the original plan, which was marked as done with basic top-level validation. Our **P8** extends that work to nested schema validation -- it builds on E2 rather than replacing it.

## Appendix C: Glossary

| Term | Meaning |
|------|---------|
| **Inline mode** | Project where `.odev.yaml` and `docker-compose.yml` live in the same directory as the code (created by `odev init`) |
| **External mode** | Project where config lives in `~/.odev/projects/<name>/` and the code lives elsewhere (created by `odev adopt`) |
| **Config directory** | Where odev stores generated files (`docker-compose.yml`, `.env`, `odoo.conf`, etc.) |
| **Working directory** | Where the actual Odoo code/addons live |
| **Regeneration** | Re-rendering templates from `odev.yaml` values to update generated config files |
| **Enterprise addons** | Odoo Enterprise Edition modules, proprietary, ~757 modules, ~500MB |
