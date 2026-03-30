# Issues Found: Enterprise Module Management

**Date:** 2026-03-30
**Tester:** giulianoRelex
**Test Case:** Setting up a shared enterprise addons directory across multiple odev projects

---

## Problems Identified

### 0. No Standard Protocol for Shared Addons Across Projects

**Severity:** Critical (Architectural)
**Impact:** Each user invents their own solution; no clear best practice for managing common/enterprise addons

**Description:**
odev has no documented standard for managing addons that should be shared across multiple projects:
- Where should enterprise modules live?
- How should shared OCA addons be organized?
- What's the recommended directory structure?
- How do you update shared addons without breaking other projects?
- How do you version-pin shared addons per Odoo version?

**Current Situation:**
Users manually figure out solutions:
```bash
# Some users do this:
~/.odev/projects/project-a/enterprise/  # Copy per project (disk waste)

# Others do this:
~/odoo-addons/enterprise/  # Random location, not discoverable

# Others do this:
/opt/odoo/enterprise/  # System-wide, permission issues

# Nowhere is this documented as "the right way"
```

**Recommended Protocol:**

```
~/.odev/addons/
├── enterprise/
│   ├── 17.0/              # Version-specific (optional)
│   └── 19.0/
├── shared-oca/
│   ├── server-tools@16.0/
│   └── server-tools@19.0/
├── customer-modules/
│   ├── my_company_app/
│   └── my_company_website/
└── README.md              # Shared addons registry
```

**odev.yaml Should Support:**
```yaml
addons_paths:
  # Project-specific addons (required)
  - "./addons"

  # Shared addons (optional, by priority)
  - ~/.odev/addons/enterprise/19.0
  - ~/.odev/addons/shared-oca
  - ~/.odev/addons/customer-modules

# Alternative: named repos for easy reference
addon_repos:
  enterprise:
    path: ~/.odev/addons/enterprise/19.0
    auto_update: false  # Warn if repo changes
    version_pin: "2026-03-30"  # Optional git tag/commit

  oca_server:
    path: ~/.odev/addons/shared-oca/server-tools
    branch: "19.0"
```

**Suggested Features:**

1. **odev init** should ask:
   ```
   Use shared enterprise clone? [y/n]
   → Path: [~/.odev/addons/enterprise]

   Use shared OCA addons? [y/n]
   → Which repos? [server-tools, website, ...] [enter to skip]
   ```

2. **New command: `odev addons list`**
   ```bash
   $ odev addons list
   PROJECT ADDONS:
     - ./addons (15 modules)

   SHARED ADDONS:
     - ~/.odev/addons/enterprise/19.0 (120 modules)
     - ~/.odev/addons/shared-oca (45 modules)

   LOCAL CACHE:
     - ~/.odev/.cache/repos/ (metadata only)
   ```

3. **New command: `odev addons pull`**
   ```bash
   $ odev addons pull enterprise
   INFO Pulling latest from ~/.odev/addons/enterprise...
   WARNING Shared repo was updated. Affected projects:
     - project-a (may need restart)
     - project-b (may need restart)

   Restart with: odev restart
   ```

4. **Documentation:** `~/.odev/addons/README.md`
   ```markdown
   # Shared Addons Registry

   ## enterprise/
   - **Path:** ~/.odev/addons/enterprise/19.0
   - **Source:** github.com/odoo/enterprise
   - **Last Updated:** 2026-03-30
   - **Used By:** elog-erp, vitalcare-erp
   - **Update:** git pull

   ## shared-oca/
   - **Path:** ~/.odev/addons/shared-oca
   - **Repos:** server-tools, website, sale-workflow
   - **Used By:** elog-erp, dgc-kiosk
   ```

**Benefits:**
- ✅ Clear directory structure for all users
- ✅ Shared repos are discoverable and documented
- ✅ Easy to share between team members ("use ~/.odev/addons")
- ✅ Version pinning prevents surprise breakage
- ✅ Commands to manage shared addons lifecycle
- ✅ Audit trail: which projects use which shared repos

**Backward Compatibility:**
- Existing projects without shared addons continue to work
- Setting `addons_paths` is optional (defaults to `["./addons"]`)
- No breaking changes

---

### 1. No Auto-Regeneration of docker-compose.yml When odev.yaml Changes

**Severity:** High
**Impact:** Confusing workflow; changes to config don't take effect without manual intervention

**Description:**
When you edit `odev.yaml` to enable enterprise or change `enterprise.path`, `odev up` does NOT regenerate `docker-compose.yml` or `config/odoo.conf`. This leaves the project in an inconsistent state.

**Current Behavior:**
```bash
# Edit odev.yaml: enterprise.enabled: false → true
odev up
# → docker-compose.yml still has old config (no /mnt/enterprise-addons mount)
```

**Expected Behavior:**
```bash
# odev should detect odev.yaml was modified and regenerate affected files:
# - docker-compose.yml (new volumes/mounts)
# - config/odoo.conf (new addons_path)
# - entrypoint.sh (new ADDONS_DIRS)
```

**Workaround:**
```bash
rm docker-compose.yml config/odoo.conf
odev up
```

**Suggested Fix:**
```python
# In odev/commands/up.py - add file hash tracking:

def _should_regenerate_config(paths: ProjectPaths, env_file: Path) -> bool:
    """Check if config files are stale relative to odev.yaml."""
    config_file = paths.odev_config
    docker_compose = paths.docker_compose_file

    if not docker_compose.exists():
        return True

    # Compare mtime: if odev.yaml is newer, regenerate
    config_mtime = config_file.stat().st_mtime
    compose_mtime = docker_compose.stat().st_mtime

    return config_mtime > compose_mtime
```

---

### 2. odoo.conf Not Generated with Enterprise addons_path

**Severity:** Critical
**Impact:** Enterprise modules mounted in Docker but not in Odoo's addon path; modules fail to load

**Description:**
When `enterprise.enabled: true` in `odev.yaml`, the generated `odoo.conf` does NOT include `/mnt/enterprise-addons` in `addons_path`.

**Current Behavior:**
```ini
# Generated odoo.conf
addons_path = /mnt/extra-addons
# Missing: /mnt/enterprise-addons
```

**Expected Behavior:**
```ini
addons_path = /mnt/extra-addons,/mnt/enterprise-addons
```

**Root Cause:**
In `odev/core/config.py`, the template is not checking `config.enterprise_habilitado` to append enterprise to addons_path.

**Suggested Fix:**
```python
# In odev/core/config.py - function generate_odoo_conf()

def generate_odoo_conf(
    config_dir: Path,
    addon_mounts: list[dict],
    enterprise_enabled: bool = False,
    enterprise_path: str = None,
) -> None:
    """Generate config/odoo.conf from template."""

    # ... existing code ...

    # Build addons_path from mounts
    addon_paths = [m["container_path"] for m in addon_mounts]

    # Append enterprise if enabled
    if enterprise_enabled:
        addon_paths.append("/mnt/enterprise-addons")

    context = {
        # ... existing ...
        "addons_path": ",".join(addon_paths),
    }
```

---

### 3. No Validation of Enterprise Path Existence

**Severity:** Medium
**Impact:** Silent failures; Docker volume mounts to non-existent path

**Description:**
When you set `enterprise.path: /invalid/path` in `odev.yaml`, odev doesn't validate that the path exists. Docker silently creates an empty mount, and Odoo finds no modules.

**Current Behavior:**
```yaml
enterprise:
  enabled: true
  path: "/home/user/.odev/addons/nonexistent"  # ← No error during odev up
```

**Expected Behavior:**
```bash
$ odev up
ERROR Enterprise path does not exist: /home/user/.odev/addons/nonexistent
Hint: Clone the enterprise repo or create the directory:
  git clone --branch 19.0 https://github.com/odoo/enterprise.git /home/user/.odev/addons/enterprise
```

**Suggested Fix:**
```python
# In odev/core/project.py - ProjectConfig.__init__()

def __init__(self, ruta_proyecto: Path) -> None:
    # ... existing load code ...

    # Validate enterprise path if enabled
    if self.enterprise_habilitado:
        enterprise_path = Path(self.datos["enterprise"]["path"])
        if not enterprise_path.is_absolute():
            enterprise_path = ruta_proyecto / enterprise_path

        if not enterprise_path.exists():
            raise FileNotFoundError(
                f"Enterprise path does not exist: {enterprise_path}\n"
                f"Clone with: git clone --branch 19.0 "
                f"https://github.com/odoo/enterprise.git {enterprise_path}"
            )
```

---

### 4. docker-compose.yml Lacks watch/sync for Enterprise Addons

**Severity:** Medium
**Impact:** Changes to enterprise module code are not hot-reloaded; requires manual restart

**Description:**
The enterprise volume is mounted as read-only without `develop.watch` rules. Other addons have hot-reload, but enterprise doesn't.

**Current Generated docker-compose.yml:**
```yaml
volumes:
  - /path/to/extra-addons:/mnt/extra-addons
  - /path/to/enterprise:/mnt/enterprise-addons  # ← No watch rule
develop:
  watch:
    - action: sync
      path: /path/to/extra-addons
      target: /mnt/extra-addons
    # Missing: enterprise watch rule
```

**Suggested Fix:**
In `templates/project/docker-compose.yml.j2`, after enterprise volume is added, include a watch rule:
```jinja
{% if enterprise_enabled %}
      - {{ enterprise_path | default('./enterprise') }}:/mnt/enterprise-addons
    # ...
    develop:
      watch:
        # ... existing addon watches ...
        - action: sync
          path: {{ enterprise_path | default('./enterprise') }}
          target: /mnt/enterprise-addons
          ignore:
            - __pycache__
            - .git
{% endif %}
```

---

### 5. No Command to Regenerate Config Files

**Severity:** Medium
**Impact:** Users must manually delete and re-run `odev up` to sync changes

**Description:**
There's no dedicated command to regenerate config files when `odev.yaml` changes. Users have to:
```bash
rm docker-compose.yml config/odoo.conf
odev up
```

**Suggested Feature:**
```bash
$ odev sync-config
INFO Regenerating docker-compose.yml...
INFO Regenerating config/odoo.conf...
INFO Regenerating entrypoint.sh...
OK Config files synced with odev.yaml
```

**Implementation:**
```python
# In odev/commands/__init__.py

@app.command()
def sync_config() -> None:
    """Regenerate config files from odev.yaml without restarting containers.

    Use this after manually editing odev.yaml to:
    - Update enterprise path
    - Add/remove addon paths
    - Change database configuration

    Does NOT stop running containers.
    """
    contexto = ObtenerContexto()
    rutas = contexto.rutas

    # Remove stale files to force regeneration
    (rutas.docker_compose_file).unlink(missing_ok=True)
    (rutas.config_dir / "odoo.conf").unlink(missing_ok=True)

    # Regenerate by simulating `odev up` config phase
    _generar_archivos_proyecto(contexto)

    success("Config files synced. Restart Odoo to apply changes: odev restart")
```

---

### 6. `odev adopt` Doesn't Detect Enterprise in External Mode

**Severity:** Low
**Impact:** Projects with existing enterprise setup lose configuration after adoption

**Description:**
When you run `odev adopt` on a project with mode=external, the detection of enterprise doesn't work properly. The command runs but enterprise flag is reset.

**Current Behavior:**
```bash
$ cd /path/to/elog-erp
$ odev adopt . --name elog-erp --no-interactive
INFO Enterprise: No  # ← Should detect enterprise/ directory
```

**Root Cause:**
In `odev/core/detect.py`, the `RepoLayout` detection doesn't check for `enterprise/` directory in external projects.

---

### 7. addons_path Hardcoded in entrypoint.sh Template

**Severity:** Low
**Impact:** entrypoint.sh doesn't reflect odev.yaml changes without regeneration

**Description:**
`entrypoint.sh` has a hardcoded `ADDONS_DIRS` list that doesn't dynamically reflect `odev.yaml` addon paths.

**Current entrypoint.sh template:**
```bash
ADDONS_DIRS="/mnt/extra-addons /mnt/enterprise-addons"
```

**Better approach:**
```bash
# Pass ADDONS_DIRS as environment variable from docker-compose
ADDONS_DIRS="${ODOO_ADDONS_DIRS:-/mnt/extra-addons}"
```

Then in docker-compose:
```yaml
environment:
  - ODOO_ADDONS_DIRS=/mnt/extra-addons /mnt/enterprise-addons
```

---

## Summary of Recommendations

| Priority | Issue | Type | Fix |
|----------|-------|------|-----|
| 🔴 Critical | No standard protocol for shared addons | Architecture | Define ~/.odev/addons/ structure + docs + commands |
| 🔴 Critical | odoo.conf missing enterprise in addons_path | Config | Check `enterprise_enabled` in config.py |
| 🔴 High | No auto-regeneration of docker-compose.yml | DX | Track file mtimes, regenerate if odev.yaml newer |
| 🟡 Medium | No validation of enterprise path | Validation | Validate path exists in ProjectConfig.__init__ |
| 🟡 Medium | No watch/sync for enterprise in docker-compose | Hot-reload | Add watch rule in template |
| 🟡 Medium | No command to resync config | DX | Add `odev sync-config` + `odev addons` commands |
| 🟢 Low | `odev adopt` doesn't detect external enterprise | Detection | Improve RepoLayout detection |
| 🟢 Low | addons_path hardcoded in entrypoint.sh | Config | Use env var from docker-compose |

---

## Test Case: Shared Enterprise Setup

**Goal:** Enable multiple odev projects to share one enterprise clone

**Setup Steps:**
```bash
# 1. Clone enterprise once to shared location
git clone --branch 19.0 https://github.com/odoo/enterprise.git ~/.odev/addons/enterprise

# 2. Edit odev.yaml in multiple projects
enterprise:
  enabled: true
  path: "/home/user/.odev/addons/enterprise"  # Shared path

# 3. Run odev up
odev up
```

**Current Issues:**
- ❌ docker-compose.yml not generated with enterprise mount
- ❌ odoo.conf missing `/mnt/enterprise-addons` in addons_path
- ❌ No validation that path exists
- ❌ No watch/sync for enterprise code changes

**All Fixed By:**
1. Implementing auto-regeneration logic
2. Updating odoo.conf template to include enterprise
3. Adding path validation
4. Adding watch rules to docker-compose template

---

## Questions for Maintainers

1. Should `odev.yaml` support **multiple** enterprise paths (e.g., for different Odoo versions)?
2. Should there be a built-in command to download/clone enterprise automatically?
3. Should enterprise modules be **optional per-module** (opt-in install) or auto-loaded?

