# SDD Specification: odev CLI Usability and Configuration Improvements

- **Date**: 2026-03-25
- **Status**: Draft
- **Source**: [proposal.md](./proposal.md)
- **Scope**: 8 improvements (P1--P8) covering config lifecycle, enterprise workflow, UX, and validation

---

## Table of Contents

1. [Cross-Cutting Concerns](#1-cross-cutting-concerns)
2. [P1 -- Config Regeneration Command (`reconfigure`)](#2-p1--config-regeneration-command-reconfigure)
3. [P2 -- Shared Enterprise Addons](#3-p2--shared-enterprise-addons)
4. [P3 -- odev.yaml as Source of Truth (auto-regen on `up`)](#4-p3--odevyaml-as-source-of-truth-auto-regen-on-up)
5. [P4 -- `load-backup` Pre-flight Checks](#5-p4--load-backup-pre-flight-checks)
6. [P5 -- `--yes` Flag for Destructive Commands](#6-p5---yes-flag-for-destructive-commands)
7. [P6 -- `adopt --force` Flag](#7-p6--adopt---force-flag)
8. [P7 -- Enterprise addons_path Ordering](#8-p7--enterprise-addons_path-ordering)
9. [P8 -- odev.yaml Schema Enforcement](#9-p8--odevyaml-schema-enforcement)
10. [Appendices](#10-appendices)

---

## 1. Cross-Cutting Concerns

### 1.1 Backward Compatibility

| Concern | Guarantee |
|---------|-----------|
| Existing `odev.yaml` files | All current files remain valid. New nested validation (P8) produces warnings, never errors. |
| Existing `.env` files | Never overwritten unless the user explicitly opts in (`--include-env` on P1). |
| Existing `docker-compose.yml` | Regenerated only on explicit command (P1) or when odev.yaml is newer (P3). Old files remain functional. |
| Existing `odoo.conf` | Same as docker-compose.yml above. |
| Registry format (`~/.odev/registry.yaml`) | No schema changes. P2 adds a new constant `ENTERPRISE_DIR` but does not alter the registry format. |
| CLI command signatures | No existing flags are removed or renamed. Only additive changes (new flags, new commands). |

### 1.2 Migration Path for Existing Projects

Projects created before this change set continue to work without modification. The improvements activate organically:

1. **No action required**: P4, P5, P7, P8 take effect automatically on CLI upgrade.
2. **Optional activation**: P1, P3 activate when the user edits `odev.yaml` and runs `odev up` or `odev reconfigure`.
3. **Explicit opt-in**: P2 requires running `odev enterprise import` to set up shared storage. P6 requires passing `--force`.

### 1.3 CLI Contract -- Command Signatures

Below are the exact command signatures introduced or modified by this spec. Existing parameters are shown for context but are not modified.

```
# P1 -- New command
odev reconfigure [--include-env] [--dry-run]

# P2 -- New subcommand group
odev enterprise import <version> <path> [--copy] [--force]
odev enterprise link [--version <version>]
odev enterprise status
odev enterprise path <version>

# P3 -- No signature change to `odev up`
odev up [--build] [--watch]

# P4 -- No signature change to `odev load-backup`
# P5 -- Modified signature
odev load-backup <backup> [--neutralize/--no-neutralize] [--yes/-y]
odev reset-db [--neutralize/--no-neutralize] [--yes/-y]

# P6 -- Modified signature
odev adopt [directory] [--name/-n <name>] [--odoo-version <ver>] [--no-interactive] [--force/-f]

# P7 -- No CLI change (template fix)
# P8 -- No CLI change (internal validation)
```

### 1.4 File Format Changes

#### odev.yaml Schema (unchanged)

No structural changes to the odev.yaml schema. The existing schema remains:

```yaml
odev_min_version: "0.2.0"
mode: external          # "inline" | "external"
odoo:
  version: "19.0"
  image: "odoo:19"
database:
  image: "pgvector/pgvector:pg16"
enterprise:
  enabled: false
  path: "./enterprise"  # May now be an absolute path like ~/.odev/enterprise/19.0
services:
  pgweb: true
paths:
  addons:
    - "./addons"
  config: "./config"
  snapshots: "./snapshots"
  logs: "./logs"
  docs: "./docs"
project:
  name: "my-project"
  description: ""
  working_dir: "/home/user/projects/my-project"  # external mode only
sdd:
  enabled: true
  language: "es"
```

#### registry.yaml (unchanged)

No changes to the registry format. The `RegistryEntry` dataclass fields remain: `nombre`, `directorio_trabajo`, `directorio_config`, `modo`, `version_odoo`, `fecha_creacion`.

#### New directory: `~/.odev/enterprise/`

```
~/.odev/
  enterprise/
    19.0/          # Enterprise addons for Odoo 19.0
      web_enterprise/
      account_accountant/
      ...
    18.0/          # Enterprise addons for Odoo 18.0
      ...
```

This directory is created on demand by `odev enterprise import`.

---

## 2. P1 -- Config Regeneration Command (`reconfigure`)

### 2.1 Functional Requirements

| ID | Requirement |
|----|-------------|
| FR-P1-001 | The command `odev reconfigure` SHALL re-render `docker-compose.yml` from the `docker-compose.yml.j2` template using current `odev.yaml` values merged with existing `.env` values. |
| FR-P1-002 | The command SHALL re-render `odoo.conf` from `odoo.conf.j2` using the same merged values. |
| FR-P1-003 | By default, the command SHALL NOT overwrite the `.env` file. The existing `.env` is read for runtime values but not regenerated. |
| FR-P1-004 | When `--include-env` is passed, the command SHALL also re-render `.env` from `env.j2`, using structural values from `odev.yaml` (ODOO_VERSION, DB image) while preserving runtime values (DB_PASSWORD, WEB_PORT, DB_NAME) from the existing `.env`. |
| FR-P1-005 | The command SHALL print a summary of files that were regenerated and the key changes detected (e.g., "enterprise_enabled: false -> true"). |
| FR-P1-006 | When `--dry-run` is passed, the command SHALL print what would change without writing any files. |
| FR-P1-007 | The command SHALL use `requerir_proyecto()` to resolve project context, working in both inline and external modes. |
| FR-P1-008 | The regeneration logic SHALL be extracted into a shared module `core/regen.py` with a public function `regenerar_configs()` reusable by P3 and P6. |
| FR-P1-009 | The command SHALL also re-render `entrypoint.sh` from `entrypoint.sh.j2` and set executable permissions (0o755). |

### 2.2 `.env` Merge Strategy

The merge between `odev.yaml` and the existing `.env` is the most critical design decision of P1. The strategy is:

**Structural values** (derived from `odev.yaml`, override `.env` when `--include-env` is used):

| `.env` Key | Source in `odev.yaml` |
|------------|-----------------------|
| `ODOO_IMAGE` | `odoo.image` |
| `ODOO_VERSION` | `odoo.version` |
| `DB_IMAGE` | `database.image` |
| `COMPOSE_PROJECT_NAME` | `project.name` |
| `PROJECT_NAME` | `project.name` |

**Runtime values** (always preserved from existing `.env`, never overwritten):

| `.env` Key | Reason |
|------------|--------|
| `DB_USER` | User may have customized |
| `DB_PASSWORD` | User may have set a secure password |
| `DB_NAME` | User may have renamed the database |
| `DB_PORT` | User may need a specific port |
| `WEB_PORT` | User may need a specific port |
| `PGWEB_PORT` | User may need a specific port |
| `DEBUGPY_PORT` | User may need a specific port |
| `MAILHOG_PORT` | User may need a specific port |
| `ADMIN_PASSWORD` | User may have set a secure password |
| `LOAD_LANGUAGE` | User preference |
| `WITHOUT_DEMO` | User preference |
| `DEBUGPY` | User preference |
| `INIT_MODULES` | User preference |

**Conflict resolution**: When `--include-env` is used:
1. Load existing `.env` values into a dict.
2. Load `odev.yaml` via `ProjectConfig`.
3. Compute new structural values from `odev.yaml`.
4. For each structural key: if the new value differs from the existing `.env` value, emit a warning: `"Updating {KEY}: '{old_value}' -> '{new_value}' (from odev.yaml)"`.
5. Merge: structural values from step 3 overwrite; all other keys preserved from step 1.
6. Any keys present in the template but missing from both sources get template defaults.

**New keys**: If the `.env` template introduces a new key not present in the existing `.env`, it is added with its template default value. A message is printed: `"Added new key: {KEY}={default_value}"`.

### 2.3 Non-Functional Requirements

| ID | Requirement |
|----|-------------|
| NFR-P1-001 | Regeneration MUST complete in under 1 second for a project with 15 addon paths. |
| NFR-P1-002 | The command MUST NOT start, stop, or restart any Docker containers. |
| NFR-P1-003 | The command MUST preserve file permissions on regenerated files (e.g., `entrypoint.sh` remains executable). |

### 2.4 User Stories

**US-P1-01**: Developer edits `odev.yaml` to enable enterprise

```
$ vim odev.yaml
  # Change enterprise.enabled: false -> true
  # Change enterprise.path: ~/.odev/enterprise/19.0

$ odev reconfigure
  Regenerating configs from odev.yaml...
    docker-compose.yml (regenerated)
      + enterprise volume mount: ~/.odev/enterprise/19.0:/mnt/enterprise-addons
    config/odoo.conf (regenerated)
      + addons_path: /mnt/enterprise-addons added (position: first)
    entrypoint.sh (regenerated)
  .env preserved (use --include-env to regenerate)
  Done. Run 'odev up' to apply changes.
```

**US-P1-02**: Developer adds a new addon path

```
$ vim odev.yaml
  # Add "- /home/user/repos/custom-addons" to paths.addons

$ odev reconfigure --dry-run
  [DRY RUN] Would regenerate:
    docker-compose.yml
      + volume: /home/user/repos/custom-addons:/mnt/extra-addons-2
      + watch: /home/user/repos/custom-addons -> /mnt/extra-addons-2
    config/odoo.conf
      + addons_path: ...,/mnt/extra-addons-2
  No files written.
```

### 2.5 Acceptance Criteria

| ID | Criterion |
|----|-----------|
| AC-P1-01 | After editing `enterprise.enabled: true` in `odev.yaml`, running `odev reconfigure` produces a `docker-compose.yml` containing the enterprise volume mount line. |
| AC-P1-02 | After `odev reconfigure`, the `.env` file has the same `DB_PASSWORD` value as before. |
| AC-P1-03 | After adding a path to `paths.addons` in `odev.yaml`, running `odev reconfigure` updates both `docker-compose.yml` (volumes + watch) and `odoo.conf` (addons_path). |
| AC-P1-04 | `odev reconfigure --dry-run` writes zero files to disk. |
| AC-P1-05 | `odev reconfigure --include-env` regenerates the `.env` file preserving runtime values. |
| AC-P1-06 | The command works in both inline and external project modes. |

### 2.6 Edge Cases

| Case | Expected Behavior |
|------|-------------------|
| `.env` file does not exist | Error: `"No .env file found. Run 'odev init' or 'odev adopt' first."` Exit code 1. |
| `odev.yaml` file does not exist | Error: `"No odev.yaml found. Run 'odev init' or 'odev adopt' first."` Exit code 1. |
| `odev.yaml` has syntax errors (invalid YAML) | Error: `"Failed to parse odev.yaml: {yaml_error}. Fix the syntax and try again."` Exit code 1. |
| `enterprise.path` points to nonexistent directory | Warning: `"Enterprise path '{path}' does not exist. Volume mount will fail at container start."` Continue regeneration. |
| Addon path in `paths.addons` does not exist | Warning: `"Addon path '{path}' does not exist. Volume mount will fail at container start."` Continue regeneration. |
| User runs `odev reconfigure` with no changes to `odev.yaml` | Regeneration still runs (files are re-rendered). Print: `"Configs regenerated (no changes detected)."` |
| Concurrent access (two terminals running `reconfigure`) | No file locking needed -- template rendering is idempotent. Last write wins. |

### 2.7 Error Messages

| Condition | Message | Exit Code |
|-----------|---------|-----------|
| No project found | `"No odev project found in current directory. Run 'odev init' or 'odev adopt' first."` | 1 |
| Missing `.env` | `"No .env file found at {path}. Run 'odev init' or 'odev adopt' to generate it."` | 1 |
| Missing `odev.yaml` | `"No odev.yaml found at {path}. Run 'odev init' or 'odev adopt' to generate it."` | 1 |
| Invalid YAML syntax | `"Failed to parse {path}: {error_detail}"` | 1 |

---

## 3. P2 -- Shared Enterprise Addons

### 3.1 Functional Requirements

| ID | Requirement |
|----|-------------|
| FR-P2-001 | `odev enterprise import <version> <path>` SHALL copy the contents of `<path>` to `~/.odev/enterprise/<version>/`. |
| FR-P2-002 | When `--copy` is NOT passed (default), `import` SHALL create a symlink `~/.odev/enterprise/<version>` pointing to `<path>` instead of copying. |
| FR-P2-003 | When `--force` is passed, `import` SHALL overwrite an existing version directory (remove and re-import). Without `--force`, it SHALL error if the version already exists. |
| FR-P2-004 | `odev enterprise link [--version <version>]` SHALL update the current project's `odev.yaml` to set `enterprise.enabled: true` and `enterprise.path` to `~/.odev/enterprise/<version>/`. If `--version` is omitted, use the project's `odoo.version`. |
| FR-P2-005 | After `odev enterprise link`, the command SHALL automatically trigger config regeneration (delegate to `regenerar_configs()` from P1). |
| FR-P2-006 | `odev enterprise status` SHALL list all versions under `~/.odev/enterprise/` with: version, path (real path if symlink), module count, size, and which projects reference each version. |
| FR-P2-007 | `odev enterprise path <version>` SHALL print the absolute path to `~/.odev/enterprise/<version>/` to stdout (suitable for `$(odev enterprise path 19.0)` in scripts). |
| FR-P2-008 | During `odev adopt`, when `layout.tiene_enterprise` is `False` and `~/.odev/enterprise/<detected_version>/` exists, the wizard SHALL ask: `"Shared enterprise addons found for {version}. Use them?"`. In `--no-interactive` mode, auto-use if available. |
| FR-P2-009 | During `odev init`, when the user enables enterprise and a shared version exists, the wizard SHALL offer to use the shared version instead of expecting a local `./enterprise` directory. |
| FR-P2-010 | A new constant `ENTERPRISE_DIR = ODEV_HOME / "enterprise"` SHALL be added to `registry.py`. |

### 3.2 Non-Functional Requirements

| ID | Requirement |
|----|-------------|
| NFR-P2-001 | Symlink mode (default) MUST NOT copy any files. The symlink target must be an absolute path. |
| NFR-P2-002 | Copy mode MUST produce a self-contained directory that works even if the source is deleted. |
| NFR-P2-003 | The `import` command MUST validate that the source path contains Odoo modules (at least one `__manifest__.py` in a subdirectory). |

### 3.3 Shared Storage Layout

```
~/.odev/
  enterprise/
    19.0/                     # Either a real directory (--copy) or a symlink
      __manifest__.py         # NOT present -- this is a directory of modules
      web_enterprise/
        __manifest__.py
        ...
      account_accountant/
        __manifest__.py
        ...
    18.0 -> /path/to/enterprise-18.0/   # Symlink example
```

### 3.4 User Stories

**US-P2-01**: Import enterprise addons from a local checkout

```
$ odev enterprise import 19.0 /home/user/odoo-enterprise
  Linking enterprise addons for version 19.0...
  Symlink: ~/.odev/enterprise/19.0 -> /home/user/odoo-enterprise
  Found 757 modules.
  Done.

$ odev enterprise status
  Version  Path                                  Modules  Projects
  -------  ------------------------------------  -------  --------
  19.0     /home/user/odoo-enterprise (symlink)  757      (none)
```

**US-P2-02**: Link enterprise to current project

```
$ cd /home/user/projects/vitalcare-erp
$ odev enterprise link
  Updating odev.yaml:
    enterprise.enabled: false -> true
    enterprise.path: ~/.odev/enterprise/19.0
  Regenerating configs...
    docker-compose.yml (regenerated)
    config/odoo.conf (regenerated)
  Done. Run 'odev up' to apply changes.
```

**US-P2-03**: Adopt picks up shared enterprise

```
$ odev adopt /home/user/projects/new-project --no-interactive
  Tipo de repositorio: odoo_addons
  ...
  Enterprise: No (local)
  Shared enterprise addons found for 19.0. Using shared enterprise.
  ...
  Proyecto 'new-project' adoptado exitosamente.
```

### 3.5 Acceptance Criteria

| ID | Criterion |
|----|-----------|
| AC-P2-01 | `odev enterprise import 19.0 /path/to/enterprise` creates `~/.odev/enterprise/19.0` as a symlink. |
| AC-P2-02 | `odev enterprise import 19.0 /path --copy` creates `~/.odev/enterprise/19.0/` as a real directory with the module files. |
| AC-P2-03 | `odev enterprise link` updates `odev.yaml` in-place with `enterprise.enabled: true` and the correct path. |
| AC-P2-04 | After `odev enterprise link`, running `odev up` starts containers with the enterprise volume mounted. |
| AC-P2-05 | `odev enterprise status` lists all available versions with module counts. |
| AC-P2-06 | `odev enterprise path 19.0` prints the path to stdout with no extra output. |
| AC-P2-07 | `odev adopt` on a project without local enterprise offers to use shared enterprise when available. |

### 3.6 Edge Cases

| Case | Expected Behavior |
|------|-------------------|
| `import` with nonexistent source path | Error: `"Source path '{path}' does not exist."` Exit code 1. |
| `import` with source containing no `__manifest__.py` | Error: `"No Odoo modules found in '{path}'. Expected directories containing __manifest__.py."` Exit code 1. |
| `import` when version already exists (no `--force`) | Error: `"Enterprise addons for version {version} already exist at {path}. Use --force to overwrite."` Exit code 1. |
| `link` when no shared enterprise exists for the project's version | Error: `"No shared enterprise addons found for version {version}. Run 'odev enterprise import {version} <path>' first."` Exit code 1. |
| `link` when no project context is found | Error: `"No odev project found in current directory."` Exit code 1. |
| Symlink target is deleted after import | Warning at `odev up` time when the volume mount fails. Not odev's responsibility to monitor. |
| `import` with version string containing path separators | Error: `"Invalid version '{version}'. Use a simple version string like '19.0'."` Exit code 1. |

### 3.7 Error Messages

| Condition | Message | Exit Code |
|-----------|---------|-----------|
| Source path missing | `"Source path '{path}' does not exist."` | 1 |
| No modules in source | `"No Odoo modules found in '{path}'. Expected directories containing __manifest__.py."` | 1 |
| Version already imported | `"Enterprise addons for version {version} already exist at {existing_path}. Use --force to overwrite."` | 1 |
| No shared enterprise for version | `"No shared enterprise addons found for version {version}. Import them first with: odev enterprise import {version} <path>"` | 1 |
| Invalid version string | `"Invalid version string '{version}'. Expected format: '19.0', '18.0', etc."` | 1 |

---

## 4. P3 -- odev.yaml as Source of Truth (auto-regen on `up`)

### 4.1 Functional Requirements

| ID | Requirement |
|----|-------------|
| FR-P3-001 | Before starting containers, `odev up` SHALL compare the mtime of `odev.yaml` against the mtime of `docker-compose.yml` and `odoo.conf`. |
| FR-P3-002 | If `odev.yaml` is newer than either generated file, `odev up` SHALL call `regenerar_configs()` (from `core/regen.py`, shared with P1) before starting containers. |
| FR-P3-003 | When auto-regeneration occurs, a warning SHALL be printed: `"odev.yaml changed since last generation. Regenerating configs..."` |
| FR-P3-004 | If `odev.yaml` is older than or equal to both generated files, NO regeneration SHALL occur (no performance penalty). |
| FR-P3-005 | The existing mtime check (`.env` vs `odoo.conf`, line 71 of `up.py`) SHALL be preserved as a separate check. The new odev.yaml check is additive. |
| FR-P3-006 | The mtime comparison SHALL work correctly in both inline mode (odev.yaml at `<root>/.odev.yaml`) and external mode (odev.yaml at `~/.odev/projects/<name>/odev.yaml`). The path is resolved via `ProjectPaths.odev_config` which already handles both modes. |

### 4.2 Non-Functional Requirements

| ID | Requirement |
|----|-------------|
| NFR-P3-001 | The mtime comparison MUST add less than 10ms to `odev up` startup time when no regeneration is needed. |
| NFR-P3-002 | Auto-regeneration MUST use the same logic as `odev reconfigure` (P1) to ensure consistent output. |

### 4.3 mtime Comparison Logic

```
odev_yaml_mtime = stat(odev.yaml).st_mtime
docker_compose_mtime = stat(docker-compose.yml).st_mtime
odoo_conf_mtime = stat(config/odoo.conf).st_mtime

needs_regen = False

if odev.yaml exists:
    if docker-compose.yml exists AND odev_yaml_mtime > docker_compose_mtime:
        needs_regen = True
    if odoo.conf exists AND odev_yaml_mtime > odoo_conf_mtime:
        needs_regen = True
    if docker-compose.yml does NOT exist:
        needs_regen = True  # File was deleted, must regenerate
    if odoo.conf does NOT exist:
        needs_regen = True  # File was deleted, must regenerate

if needs_regen:
    regenerar_configs(contexto, rutas)
```

The files checked are:
- `docker-compose.yml` -- the primary orchestration file
- `config/odoo.conf` -- the Odoo configuration file

The `.env` file is NOT included in the mtime check because it contains user-edited runtime values and should not be auto-regenerated.

### 4.4 User Stories

**US-P3-01**: Developer edits `odev.yaml` then runs `odev up`

```
$ vim odev.yaml
  # Change enterprise.enabled: false -> true

$ odev up
  odev.yaml changed since last generation. Regenerating configs...
    docker-compose.yml (regenerated)
    config/odoo.conf (regenerated)
  Iniciando entorno...
  Entorno iniciado correctamente.
    Odoo:  http://localhost:8069
    pgweb: http://localhost:8081
```

**US-P3-02**: Developer runs `odev up` with no changes

```
$ odev up
  Iniciando entorno...
  Entorno iniciado correctamente.
    Odoo:  http://localhost:8069
    pgweb: http://localhost:8081
```

(No regeneration message -- files are up to date.)

### 4.5 Acceptance Criteria

| ID | Criterion |
|----|-----------|
| AC-P3-01 | Editing `odev.yaml` and running `odev up` triggers automatic regeneration with a warning message. |
| AC-P3-02 | Running `odev up` when `odev.yaml` has not changed produces no regeneration and no warning. |
| AC-P3-03 | The mtime comparison works for external projects where `odev.yaml` is in `~/.odev/projects/<name>/`. |
| AC-P3-04 | If `docker-compose.yml` or `odoo.conf` is manually deleted, `odev up` regenerates them. |
| AC-P3-05 | The existing `.env` -> `odoo.conf` mtime check still works independently. |

### 4.6 Edge Cases

| Case | Expected Behavior |
|------|-------------------|
| `odev.yaml` does not exist | Skip the mtime check entirely. Fall through to existing behavior. Log at DEBUG level. |
| `docker-compose.yml` does not exist | Trigger regeneration (the file is needed for `docker compose up`). |
| `odoo.conf` does not exist | Trigger regeneration. |
| `odev.yaml` has the same mtime as generated files (clock skew, copy) | Do NOT regenerate. The check is strictly `>` (newer), not `>=`. |
| File system does not support mtime (network mount, etc.) | Degrade gracefully -- if `stat()` fails, skip the check and log a warning. |
| User touches `odev.yaml` without changing content (`touch odev.yaml`) | Regeneration triggers. This is by design -- the mtime changed, and regeneration is idempotent. |

---

## 5. P4 -- `load-backup` Pre-flight Checks

### 5.1 Functional Requirements

| ID | Requirement |
|----|-------------|
| FR-P4-001 | Before the confirmation prompt, `load-backup` SHALL verify that the `db` service has a running container. |
| FR-P4-002 | If the `db` service is not running, the command SHALL print an error message and exit with code 1. |
| FR-P4-003 | A new method `is_service_running(service: str) -> bool` SHALL be added to the `DockerCompose` class in `core/docker.py`. |
| FR-P4-004 | The `is_service_running()` method SHALL use `ps_parsed()` to get structured service status and check for `State == "running"`. |
| FR-P4-005 | The pre-flight check SHALL occur BEFORE the backup validation (zip check, dump detection) to fail as fast as possible. |

### 5.2 `is_service_running()` Specification

```python
def is_service_running(self, service: str) -> bool:
    """Check if a specific service has a running container.

    Args:
        service: Name of the Docker Compose service (e.g., "db", "web").

    Returns:
        True if the service has at least one container in "running" state.
    """
```

The method uses `ps_parsed()` which already handles both JSON array and JSON-per-line output from `docker compose ps --format json`. The check iterates over results and matches `svc.get("Service") == service and svc.get("State") == "running"`.

### 5.3 Non-Functional Requirements

| ID | Requirement |
|----|-------------|
| NFR-P4-001 | The pre-flight check MUST add less than 2 seconds to command startup (dominated by `docker compose ps` execution). |
| NFR-P4-002 | The `is_service_running()` method MUST be reusable by other commands that need container status checks. |

### 5.4 User Stories

**US-P4-01**: `load-backup` when containers are stopped

```
$ odev load-backup backup.zip
  Error: The database service is not running. Start the environment first with 'odev up'.
```

**US-P4-02**: `load-backup` when containers are running

```
$ odev load-backup backup.zip
  Backup: backup.zip (245.3 MB)
    Dump: dump.sql (SQL)
    Filestore: si
  Esto REEMPLAZARA la base de datos 'odoo_db' con el contenido del backup!
  Continuar? [y/N]:
```

### 5.5 Acceptance Criteria

| ID | Criterion |
|----|-----------|
| AC-P4-01 | Running `odev load-backup` with containers stopped prints the error message and exits with code 1. |
| AC-P4-02 | Running `odev load-backup` with containers running proceeds to backup validation and confirmation. |
| AC-P4-03 | The error appears before any confirmation prompt. |
| AC-P4-04 | The error appears before the backup zip is opened or validated. |

### 5.6 Edge Cases

| Case | Expected Behavior |
|------|-------------------|
| `docker compose ps` fails (Docker daemon not running) | The `_run()` call inside `ps()` raises `subprocess.CalledProcessError`. Catch and display: `"Failed to check container status. Is Docker running?"` Exit code 1. |
| `db` service exists but is in "exited" or "restarting" state | `is_service_running()` returns `False`. Pre-flight fails. |
| `db` service is "created" but not "running" | `is_service_running()` returns `False`. Pre-flight fails. |
| No containers exist at all (never started) | `ps_parsed()` returns `[]`. `is_service_running()` returns `False`. |
| The `docker-compose.yml` is missing | `DockerCompose.__init__` will fail earlier. Not this command's concern. |

### 5.7 Error Messages

| Condition | Message | Exit Code |
|-----------|---------|-----------|
| db not running | `"The database service is not running. Start the environment first with 'odev up'."` | 1 |
| Docker not reachable | `"Failed to check container status. Is Docker running?"` | 1 |

### 5.8 Placement in `load_backup.py`

The pre-flight check is inserted after the `DockerCompose` instantiation (line 59) and BEFORE the zip validation (line 62). This ordering is:

1. Resolve project context (existing, lines 47--48)
2. Load `.env` values (existing, lines 50--52)
3. Create DockerCompose instance (existing, line 59)
4. **NEW: Pre-flight check -- is `db` running?**
5. Validate zip file (existing, lines 62--78)
6. Show backup info (existing, lines 83--86)
7. Confirmation prompt (existing, lines 88--91)

---

## 6. P5 -- `--yes` Flag for Destructive Commands

### 6.1 Functional Requirements

| ID | Requirement |
|----|-------------|
| FR-P5-001 | `load-backup` SHALL accept `--yes` / `-y` flag that skips the `typer.confirm()` call. |
| FR-P5-002 | `reset-db` SHALL accept `--yes` / `-y` flag that skips the `typer.confirm()` call. |
| FR-P5-003 | When `--yes` is passed, the warning message SHALL still be printed (only the interactive confirmation is skipped). |
| FR-P5-004 | When stdin is not a TTY (piped input), the command SHALL behave as if `--yes` was NOT passed -- it will fail at the `typer.confirm()` prompt. Users must explicitly pass `--yes` for non-interactive use. |
| FR-P5-005 | The default value of `--yes` SHALL be `False` (confirmation required by default). |

### 6.2 Non-Functional Requirements

| ID | Requirement |
|----|-------------|
| NFR-P5-001 | The `--yes` flag MUST NOT affect any behavior other than skipping the confirmation prompt. |
| NFR-P5-002 | Help text for `--yes` MUST clearly state that it skips confirmation for automation use. |

### 6.3 Commands Affected

| Command | Current Confirmation | After P5 |
|---------|---------------------|----------|
| `load-backup` | `typer.confirm("Continuar?", default=False)` at line 89 | `if not yes and not typer.confirm(...)` |
| `reset-db` | `typer.confirm("Estas seguro?", default=False)` at line 40 | `if not yes and not typer.confirm(...)` |

### 6.4 User Stories

**US-P5-01**: Automated backup loading

```
$ odev load-backup backup.zip --yes
  Backup: backup.zip (245.3 MB)
    Dump: dump.sql (SQL)
    Filestore: si
  Esto REEMPLAZARA la base de datos 'odoo_db' con el contenido del backup!
  Extrayendo backup...
  ...
  Backup cargado en 'odoo_db'. Acceder en http://localhost:8069
```

**US-P5-02**: Script usage

```bash
#!/bin/bash
# Automated backup restore for CI
odev up
sleep 30  # wait for containers
odev load-backup /backups/latest.zip --yes --no-neutralize
```

**US-P5-03**: Short flag

```
$ odev load-backup backup.zip -y
```

### 6.5 Acceptance Criteria

| ID | Criterion |
|----|-----------|
| AC-P5-01 | `odev load-backup backup.zip --yes` completes without interactive prompts. |
| AC-P5-02 | `odev load-backup backup.zip -y` completes without interactive prompts. |
| AC-P5-03 | `odev reset-db --yes` completes without interactive prompts. |
| AC-P5-04 | Without `--yes`, interactive confirmation works exactly as before. |
| AC-P5-05 | The warning message is displayed even when `--yes` is used. |

### 6.6 Edge Cases

| Case | Expected Behavior |
|------|-------------------|
| `--yes` combined with `--no-neutralize` | Both flags work independently. Confirmation skipped, neutralization skipped. |
| `--yes` passed but db not running (P4) | Pre-flight check (P4) still fires. `--yes` only affects the confirmation prompt. |
| `--yes` with an invalid backup file | Validation errors still fire. `--yes` only skips the confirmation. |

---

## 7. P6 -- `adopt --force` Flag

### 7.1 Functional Requirements

| ID | Requirement |
|----|-------------|
| FR-P6-001 | `adopt` SHALL accept `--force` / `-f` flag that allows re-adopting an already-adopted project. |
| FR-P6-002 | When `--force` is passed and the project name already exists in the registry, the command SHALL remove the existing registry entry and delete the existing config directory (`~/.odev/projects/<name>/`). |
| FR-P6-003 | When `--force` is passed and the target directory has a `.odev.yaml` file, the command SHALL proceed instead of exiting with error. |
| FR-P6-004 | After force-cleanup, the command SHALL proceed with the normal adopt flow (detection, wizard, config generation, registration). |
| FR-P6-005 | Without `--force`, the existing error messages SHALL be preserved but enhanced with a hint to use `--force`. |
| FR-P6-006 | The `--force` flag SHALL NOT delete the working directory (the actual project code). Only the odev config directory under `~/.odev/projects/` is removed. |

### 7.2 What Gets Deleted vs Preserved

| Item | With `--force` | Without `--force` |
|------|----------------|-------------------|
| Registry entry (`~/.odev/registry.yaml`) | Removed, then re-created | Error if exists |
| Config directory (`~/.odev/projects/<name>/`) | Removed via `shutil.rmtree()`, then re-created | Not touched |
| `.odev.yaml` in working directory | Ignored (not deleted) | Causes error |
| `.env` in config directory | Deleted (part of config dir removal) | Not touched |
| `docker-compose.yml` in config directory | Deleted (part of config dir removal) | Not touched |
| Working directory (actual code) | **NEVER deleted** | Not touched |
| Docker volumes (data) | **NEVER deleted** | Not touched |

### 7.3 Non-Functional Requirements

| ID | Requirement |
|----|-------------|
| NFR-P6-001 | The `--force` flag MUST print a warning before deleting the config directory. |
| NFR-P6-002 | The `--force` operation MUST be atomic with respect to the registry: if regeneration fails after cleanup, the project should not be left in a half-registered state. |

### 7.4 User Stories

**US-P6-01**: Re-adopt after configuration issues

```
$ odev adopt --force
  Warning: Removing existing project 'vitalcare-erp' from registry...
  Warning: Removing config directory: ~/.odev/projects/vitalcare-erp/
  Tipo de repositorio: odoo_sh
  Modulos encontrados: 45
  ...
  Proyecto 'vitalcare-erp' adoptado exitosamente.
```

**US-P6-02**: Adopt without `--force` when project exists (improved error)

```
$ odev adopt
  Error: Project 'vitalcare-erp' already exists in the registry. Use --force to re-adopt.
```

**US-P6-03**: Adopt with `.odev.yaml` present and `--force`

```
$ odev adopt --force .
  Warning: Removing existing project 'my-project' from registry...
  ...
  Proyecto 'my-project' adoptado exitosamente.
```

### 7.5 Acceptance Criteria

| ID | Criterion |
|----|-----------|
| AC-P6-01 | `odev adopt --force` on an already-adopted project succeeds. |
| AC-P6-02 | After `odev adopt --force`, the registry entry points to the new config directory. |
| AC-P6-03 | After `odev adopt --force`, the generated files reflect the current layout detection. |
| AC-P6-04 | Without `--force`, the existing error message includes a hint about `--force`. |
| AC-P6-05 | `odev adopt --force` on a project with `.odev.yaml` in the working directory succeeds. |
| AC-P6-06 | The working directory is never deleted by `--force`. |

### 7.6 Edge Cases

| Case | Expected Behavior |
|------|-------------------|
| `--force` on a project that does not exist in registry | Proceed normally (no cleanup needed). The `.odev.yaml` check is bypassed if `--force`. |
| `--force` when config directory was manually deleted | Proceed normally. The registry entry is removed, `shutil.rmtree` on nonexistent path is a no-op (use `ignore_errors=True` or check `exists()`). |
| `--force` combined with `--no-interactive` | Both flags work. Force cleanup, then non-interactive adopt. |
| `--force` when Docker containers are still running from old config | Containers are NOT stopped. The user is responsible for `odev down` first. Print a warning if containers are detected: `"Warning: Containers may still be running from the previous configuration. Run 'odev down' if needed."` |
| `--force` with a different `--name` than the existing project | The new name is used. If a different name already exists, that entry is cleaned. The old-name entry remains (it was not referenced). |

### 7.7 Error Messages

| Condition | Message | Exit Code |
|-----------|---------|-----------|
| Project exists, no `--force` | `"Project '{name}' already exists in the registry. Use 'odev adopt --force' to re-adopt."` | 1 |
| `.odev.yaml` exists, no `--force` | `"'{path}' is already an odev project (has .odev.yaml). Use 'odev up' directly or '--force' to re-adopt."` | 1 |

---

## 8. P7 -- Enterprise addons_path Ordering

### 8.1 Functional Requirements

| ID | Requirement |
|----|-------------|
| FR-P7-001 | In `odoo.conf.j2`, when `enterprise_enabled` is true, `/mnt/enterprise-addons` SHALL appear FIRST in the `addons_path` value, before any `/mnt/extra-addons*` paths. |
| FR-P7-002 | When `enterprise_enabled` is false, the `addons_path` SHALL not include `/mnt/enterprise-addons` (existing behavior, unchanged). |
| FR-P7-003 | Both template branches (with `addon_container_paths` defined and the fallback) SHALL be updated. |

### 8.2 Template Changes

**Current** (`odoo.conf.j2` lines 2--6):

```jinja
{% if addon_container_paths is defined %}
addons_path = {{ addon_container_paths | join(',') }}{% if enterprise_enabled %},/mnt/enterprise-addons{% endif %}
{% else %}
addons_path = /mnt/extra-addons{% if enterprise_enabled %},/mnt/enterprise-addons{% endif %}
{% endif %}
```

**Proposed**:

```jinja
{% if addon_container_paths is defined %}
addons_path = {% if enterprise_enabled %}/mnt/enterprise-addons,{% endif %}{{ addon_container_paths | join(',') }}
{% else %}
addons_path = {% if enterprise_enabled %}/mnt/enterprise-addons,{% endif %}/mnt/extra-addons
{% endif %}
```

### 8.3 Non-Functional Requirements

| ID | Requirement |
|----|-------------|
| NFR-P7-001 | This is a correctness fix. Enterprise modules (e.g., `web_enterprise`) MUST override their CE counterparts (e.g., `web`) in the module resolution order. Odoo resolves modules by scanning `addons_path` left to right, using the first match. |
| NFR-P7-002 | Projects without enterprise enabled MUST NOT be affected. |

### 8.4 User Stories

**US-P7-01**: Generated `odoo.conf` with enterprise enabled

```ini
[options]
addons_path = /mnt/enterprise-addons,/mnt/extra-addons,/mnt/extra-addons-1,/mnt/extra-addons-2
```

**US-P7-02**: Generated `odoo.conf` without enterprise

```ini
[options]
addons_path = /mnt/extra-addons,/mnt/extra-addons-1,/mnt/extra-addons-2
```

### 8.5 Acceptance Criteria

| ID | Criterion |
|----|-----------|
| AC-P7-01 | With `enterprise_enabled=True`, the generated `odoo.conf` has `/mnt/enterprise-addons` as the FIRST entry in `addons_path`. |
| AC-P7-02 | With `enterprise_enabled=False`, the generated `odoo.conf` has no `/mnt/enterprise-addons` in `addons_path`. |
| AC-P7-03 | With `enterprise_enabled=True` and no `addon_container_paths`, the fallback path is `/mnt/enterprise-addons,/mnt/extra-addons`. |
| AC-P7-04 | Existing projects regenerate correctly after the template change (e.g., via P1 or P3). |

### 8.6 Edge Cases

| Case | Expected Behavior |
|------|-------------------|
| Enterprise enabled but enterprise volume not mounted | Odoo will log a warning about missing path but continue. Not odev's problem -- the `docker-compose.yml` template already handles the mount conditionally. |
| Single addon path with enterprise | `addons_path = /mnt/enterprise-addons,/mnt/extra-addons` |
| No addon paths with enterprise (edge) | `addons_path = /mnt/enterprise-addons,/mnt/extra-addons` (fallback branch) |

---

## 9. P8 -- odev.yaml Schema Enforcement

### 9.1 Functional Requirements

| ID | Requirement |
|----|-------------|
| FR-P8-001 | `_validar_esquema()` in `project.py` SHALL validate nested key names within each top-level section. |
| FR-P8-002 | Unknown nested keys SHALL produce a warning: `"Unknown key '{key}' in section '{section}' of {file}. Possible typo."` |
| FR-P8-003 | Type mismatches for nested values SHALL produce a warning: `"Key '{section}.{key}' in {file} should be {expected_type}, but is {actual_type}."` |
| FR-P8-004 | All new validations SHALL produce warnings (not errors) for forward compatibility. |
| FR-P8-005 | Valid configurations SHALL produce no warnings. |
| FR-P8-006 | The nested schema SHALL be defined as a constant `_ESQUEMA_NESTED` mapping section names to dicts of key names and expected types. |

### 9.2 Nested Schema Definition

```python
_ESQUEMA_NESTED: dict[str, dict[str, type | tuple[type, ...]]] = {
    "odoo": {
        "version": str,
        "image": str,
    },
    "database": {
        "image": str,
    },
    "enterprise": {
        "enabled": bool,
        "path": str,
    },
    "services": {
        "pgweb": bool,
    },
    "paths": {
        "addons": (list, str),  # list of strings, or a single string (legacy compat)
        "config": str,
        "snapshots": str,
        "logs": str,
        "docs": str,
    },
    "project": {
        "name": str,
        "description": str,
        "working_dir": str,
    },
    "sdd": {
        "enabled": bool,
        "language": str,
    },
}
```

### 9.3 Validation Logic

The enhanced `_validar_esquema()` performs two passes:

**Pass 1 (existing)**: Top-level key validation (unknown keys, type mismatches).

**Pass 2 (new)**: For each top-level key that is a `dict` and has an entry in `_ESQUEMA_NESTED`:
1. Iterate over the actual nested keys.
2. If a key is not in the schema for that section, emit warning about unknown key.
3. If a key is in the schema, check the value type. If mismatch, emit warning.

### 9.4 Non-Functional Requirements

| ID | Requirement |
|----|-------------|
| NFR-P8-001 | Warnings MUST NOT prevent the project from loading. `ProjectConfig.__init__` continues after validation. |
| NFR-P8-002 | Unknown top-level keys that are also not in `_ESQUEMA_NESTED` continue to produce the existing warning (no regression). |
| NFR-P8-003 | The `mode` key and `sdd` key remain in the "known keys" set. |

### 9.5 Keys Validated

| Section | Key | Type | Warning on Mismatch |
|---------|-----|------|---------------------|
| `odoo` | `version` | `str` | "should be str, but is {actual}" |
| `odoo` | `image` | `str` | "should be str, but is {actual}" |
| `database` | `image` | `str` | "should be str, but is {actual}" |
| `enterprise` | `enabled` | `bool` | "should be bool, but is {actual}" |
| `enterprise` | `path` | `str` | "should be str, but is {actual}" |
| `services` | `pgweb` | `bool` | "should be bool, but is {actual}" |
| `paths` | `addons` | `list` or `str` | "should be list or str, but is {actual}" |
| `paths` | `config` | `str` | "should be str, but is {actual}" |
| `paths` | `snapshots` | `str` | "should be str, but is {actual}" |
| `paths` | `logs` | `str` | "should be str, but is {actual}" |
| `paths` | `docs` | `str` | "should be str, but is {actual}" |
| `project` | `name` | `str` | "should be str, but is {actual}" |
| `project` | `description` | `str` | "should be str, but is {actual}" |
| `project` | `working_dir` | `str` | "should be str, but is {actual}" |
| `sdd` | `enabled` | `bool` | "should be bool, but is {actual}" |
| `sdd` | `language` | `str` | "should be str, but is {actual}" |

### 9.6 User Stories

**US-P8-01**: Typo in nested key

```
$ cat odev.yaml
  enterprise:
    enbled: true    # typo!

$ odev up
  Warning: Unknown key 'enbled' in section 'enterprise' of .odev.yaml. Possible typo.
  Iniciando entorno...
```

**US-P8-02**: Wrong type for nested value

```
$ cat odev.yaml
  enterprise:
    enabled: "yes"  # should be bool

$ odev up
  Warning: Key 'enterprise.enabled' in .odev.yaml should be bool, but is str.
  Iniciando entorno...
```

**US-P8-03**: Valid config

```
$ odev up
  Iniciando entorno...
  Entorno iniciado correctamente.
```

(No warnings.)

### 9.7 Acceptance Criteria

| ID | Criterion |
|----|-----------|
| AC-P8-01 | `enterprise.enbled: true` produces warning about unknown key `enbled` in section `enterprise`. |
| AC-P8-02 | `enterprise.enabled: "yes"` produces warning about expected `bool`, got `str`. |
| AC-P8-03 | `paths.addons: 42` (int) produces warning about expected `list` or `str`, got `int`. |
| AC-P8-04 | A fully valid `odev.yaml` produces zero warnings. |
| AC-P8-05 | Unknown top-level keys still produce warnings (existing behavior preserved). |
| AC-P8-06 | The project loads and operates normally even when warnings are emitted. |

### 9.8 Edge Cases

| Case | Expected Behavior |
|------|-------------------|
| Top-level key is not a dict but schema expects one (e.g., `enterprise: true`) | Existing pass-1 check catches this ("should be dict, but is bool"). Pass-2 skips non-dict values. |
| Nested key has `None` value (e.g., `enterprise.path: null`) | `None` is `NoneType`, not `str`. Emit warning: "should be str, but is NoneType". |
| Extra nested keys from future odev versions | Warning only (not error). Forward compatibility preserved. |
| `paths.addons` is a string (legacy format) | Valid -- the type spec is `(list, str)`. No warning. The existing coercion in `ProjectConfig.__init__` converts it to a list. |
| Empty `odev.yaml` file | `yaml.safe_load` returns `None` or `{}`. No crash. Defaults are applied. |

### 9.9 Error Messages

All P8 messages are warnings (not errors). They do not cause exit.

| Condition | Message |
|-----------|---------|
| Unknown nested key | `"Unknown key '{key}' in section '{section}' of {file}. Possible typo."` |
| Type mismatch (single type) | `"Key '{section}.{key}' in {file} should be {expected}, but is {actual}."` |
| Type mismatch (tuple of types) | `"Key '{section}.{key}' in {file} should be {type1} or {type2}, but is {actual}."` |

---

## 10. Appendices

### 10.1 Appendix A -- New File: `core/regen.py` Public API

This file is the shared regeneration engine used by P1, P3, and P6.

```python
def regenerar_configs(
    contexto: ProjectContext,
    rutas: ProjectPaths,
    include_env: bool = False,
    dry_run: bool = False,
) -> list[str]:
    """Re-read odev.yaml + .env, re-render docker-compose.yml, odoo.conf, and entrypoint.sh.

    Args:
        contexto: Resolved project context.
        rutas: Project paths instance.
        include_env: If True, also regenerate the .env file.
        dry_run: If True, compute changes but do not write files.

    Returns:
        List of file paths (relative) that were regenerated.
    """
```

The function performs these steps:
1. Load `odev.yaml` via `ProjectConfig(rutas.root)`.
2. Load existing `.env` via `load_env(rutas.env_file)`.
3. Build template values by merging `odev.yaml` structural values with `.env` runtime values (see P1 merge strategy, section 2.2).
4. Render `docker-compose.yml.j2` -> `docker-compose.yml`.
5. Render `odoo.conf.j2` -> `config/odoo.conf` (using `generate_odoo_conf()`).
6. Render `entrypoint.sh.j2` -> `entrypoint.sh`, set permissions to 0o755.
7. Optionally render `env.j2` -> `.env` if `include_env` is True.
8. Return list of regenerated file names.

### 10.2 Appendix B -- New File: `commands/reconfigure.py` Structure

```python
def reconfigure(
    include_env: bool = typer.Option(
        False,
        "--include-env",
        help="Also regenerate the .env file (preserving runtime values).",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show what would change without writing files.",
    ),
) -> None:
    """Regenerate config files (docker-compose.yml, odoo.conf) from odev.yaml."""
```

### 10.3 Appendix C -- New File: `commands/enterprise.py` Structure

```python
app = typer.Typer(name="enterprise", help="Manage shared enterprise addons.")

@app.command()
def import_enterprise(
    version: str = typer.Argument(..., help="Odoo version (e.g., 19.0)"),
    path: Path = typer.Argument(..., help="Path to enterprise addons directory"),
    copy: bool = typer.Option(False, "--copy", help="Copy instead of symlink"),
    force: bool = typer.Option(False, "--force", help="Overwrite existing version"),
) -> None: ...

@app.command()
def link(
    version: str = typer.Option(None, "--version", help="Override Odoo version"),
) -> None: ...

@app.command()
def status() -> None: ...

@app.command()
def path(
    version: str = typer.Argument(..., help="Odoo version"),
) -> None: ...
```

### 10.4 Appendix D -- Dependency Graph

```
Independent (Batch 1):
  P7 (enterprise ordering)     -- template fix
  P5 (--yes flag)              -- flag addition
  P4 (pre-flight checks)       -- guard addition
  P8 (schema enforcement)      -- validation enhancement

Chain (Batch 2):
  P1 (reconfigure) ──> P3 (auto-regen on up)
       │
       └──> P6 (adopt --force, delegates cleanup + regen)

Depends on P1 (Batch 3):
  P2 (shared enterprise) ──> P1 (link triggers regen)
```

### 10.5 Appendix E -- File Impact Matrix

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

### 10.6 Appendix F -- Implementation Order

```
Batch 1 (Quick Wins):       P7 -> P5 -> P4 -> P8           ~0.5 day
Batch 2 (Config Lifecycle):  P1 -> P3 -> P6                 ~1 day
Batch 3 (Enterprise):        P2                              ~1 day
                                                             --------
                                                     Total:  ~2.5 days
```
