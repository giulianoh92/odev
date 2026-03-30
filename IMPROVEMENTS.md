# Proposed Improvements: Enterprise Module Support

**Target:** odev v0.3.0+
**Priority:** High
**Scope:** Better enterprise module management across multiple projects

---

## Improvement 0: Standard Shared Addons Protocol

### File: `~/.odev/addons/README.md` (NEW - User-Facing Documentation)

```markdown
# odev Shared Addons Registry

Central location for addons shared across multiple projects.

## Directory Structure

\`\`\`
~/.odev/addons/
├── README.md              # This file - registry documentation
├── .registry.yaml         # Machine-readable addon metadata
├── enterprise/
│   ├── 17.0/             # Version-specific enterprise
│   ├── 18.0/
│   └── 19.0/
├── oca/
│   ├── server-tools@19.0/
│   ├── website@19.0/
│   └── sale-workflow@19.0/
└── customer/
    ├── mycompany_app/
    └── mycompany_tools/
\`\`\`

## Managing Shared Addons

### Clone Enterprise
\`\`\`bash
cd ~/.odev/addons
git clone --branch 19.0 https://github.com/odoo/enterprise.git enterprise/19.0
\`\`\`

### Clone OCA Repos
\`\`\`bash
# server-tools
git clone --branch 19.0 https://github.com/OCA/server-tools.git oca/server-tools@19.0

# website
git clone --branch 19.0 https://github.com/OCA/website.git oca/website@19.0
\`\`\`

## Registry File Format (.registry.yaml)

\`\`\`yaml
addons:
  enterprise:
    19.0:
      path: "./enterprise/19.0"
      source: "https://github.com/odoo/enterprise"
      branch: "19.0"
      last_updated: "2026-03-30"
      used_by:
        - elog-erp
        - vitalcare-erp

  oca_server_tools:
    19.0:
      path: "./oca/server-tools@19.0"
      source: "https://github.com/OCA/server-tools"
      branch: "19.0"
      last_updated: "2026-03-28"
      used_by:
        - elog-erp
        - dgc-kiosk

  mycompany_app:
    path: "./customer/mycompany_app"
    internal: true
    used_by:
      - elog-erp
\`\`\`

## Using in Projects

### In odev.yaml:
\`\`\`yaml
addons_paths:
  - "./addons"                                    # Project-specific
  - "~/.odev/addons/enterprise/19.0"             # Shared enterprise
  - "~/.odev/addons/oca/server-tools@19.0"       # Shared OCA
  - "~/.odev/addons/customer/mycompany_app"      # Shared internal
\`\`\`

Or with named repositories:
\`\`\`yaml
addon_repos:
  enterprise:
    path: "~/.odev/addons/enterprise/19.0"
    auto_update: false

  oca:
    - path: "~/.odev/addons/oca/server-tools@19.0"
    - path: "~/.odev/addons/oca/website@19.0"

  internal:
    path: "~/.odev/addons/customer/mycompany_app"
\`\`\`

## Commands

\`\`\`bash
# List all shared addons used by this project
odev addons list

# List all shared addons globally
odev addons list --global

# Check for updates to shared repos
odev addons check-updates

# Pull latest from shared repos
odev addons pull enterprise

# Generate registry metadata
odev addons sync-registry

# Show which projects use a shared addon
odev addons used-by enterprise/19.0
\`\`\`

## Best Practices

1. **Version your repos:** Use naming like `repo@version` (e.g., `server-tools@19.0`)
2. **Update carefully:** Shared addons affect all dependent projects
3. **Pin commits:** Use `git tag` to mark stable versions
4. **Document changes:** Update `.registry.yaml` after pulling
5. **Test impacts:** Before updating, run tests in all dependent projects

## Gotchas

- ⚠️ Updating a shared repo will affect ALL projects that use it
- ⚠️ Path references are absolute; moving ~/.odev/addons requires git config updates
- ⚠️ Symlinks may not work reliably in Docker; use absolute paths instead
\`\`\`

---

### File: `odev/commands/addons.py` (NEW)

```python
"""Comando `odev addons` — gestionar addons compartidos.

Permite listar, actualizar y gestionar addons compartidos entre proyectos.
"""

import typer
from pathlib import Path
from typing import Optional

from odev.core.console import console, info, success, warning, error
from odev.core.registry import PROJECTS_DIR
from odev.core.context import ObtenerContexto

app = typer.Typer(help="Gestionar addons compartidos entre proyectos")


@app.command()
def list(global_scope: bool = typer.Option(False, "--global", help="Listar todos los addons compartidos")) -> None:
    """Lista los addons compartidos usados por este proyecto (o globalmente)."""

    if global_scope:
        _list_global_addons()
    else:
        _list_project_addons()


def _list_project_addons() -> None:
    """List addons used by current project."""
    try:
        contexto = ObtenerContexto()
    except FileNotFoundError:
        error("Proyecto no encontrado")
        raise typer.Exit(1)

    config = contexto.config
    addon_paths = config.rutas_addons

    console.print("\n[bold]PROJECT ADDONS:[/bold]")
    for path in addon_paths:
        num_modules = _count_odoo_modules(Path(path))
        console.print(f"  📁 {path} ({num_modules} modules)")

    # Check for shared addons (paths outside project root)
    shared = [p for p in addon_paths if not Path(p).is_relative_to(contexto.rutas.root)]
    if shared:
        console.print("\n[bold]SHARED ADDONS:[/bold]")
        for path in shared:
            num_modules = _count_odoo_modules(Path(path))
            console.print(f"  🔗 {path} ({num_modules} modules)")


def _list_global_addons() -> None:
    """List all shared addons in ~/.odev/addons/."""
    addons_dir = Path.home() / ".odev" / "addons"

    if not addons_dir.exists():
        info(f"No addons found at {addons_dir}")
        return

    console.print("\n[bold]SHARED ADDONS REGISTRY:[/bold]")
    console.print(f"Location: {addons_dir}\n")

    for category_dir in sorted(addons_dir.iterdir()):
        if category_dir.name.startswith(".") or not category_dir.is_dir():
            continue

        console.print(f"[cyan]{category_dir.name.upper()}[/cyan]")

        for repo_dir in sorted(category_dir.iterdir()):
            if repo_dir.is_dir() and not repo_dir.name.startswith("."):
                num_modules = _count_odoo_modules(repo_dir)
                git_info = _get_git_info(repo_dir)
                console.print(
                    f"  📁 {repo_dir.name:<30} ({num_modules:>3} modules)  "
                    f"[dim]{git_info}[/dim]"
                )

        console.print()


@app.command()
def check_updates() -> None:
    """Verifica si hay actualizaciones en los addons compartidos usados."""

    try:
        contexto = ObtenerContexto()
    except FileNotFoundError:
        error("Proyecto no encontrado")
        raise typer.Exit(1)

    addon_paths = contexto.config.rutas_addons

    # Filter to shared paths only
    shared_paths = [
        p for p in addon_paths
        if not Path(p).is_relative_to(contexto.rutas.root)
    ]

    if not shared_paths:
        info("No shared addons found in this project")
        return

    console.print("[bold]Checking for updates...[/bold]\n")

    for path in shared_paths:
        repo_path = Path(path)
        if not repo_path.is_dir():
            warning(f"  ⚠ {path} does not exist")
            continue

        # Check git status
        result = _check_git_updates(repo_path)
        if result["has_updates"]:
            console.print(
                f"  ⬆ [yellow]{path}[/yellow]\n"
                f"     {result['message']}\n"
            )
        else:
            console.print(f"  ✓ {path} (up to date)")


@app.command()
def pull(addon_name: str = typer.Argument(..., help="Name of addon repo to pull (e.g., 'enterprise')")) -> None:
    """Actualiza un addon compartido desde su repositorio remoto."""

    addons_dir = Path.home() / ".odev" / "addons"

    # Find the addon directory
    addon_path = None
    for category_dir in addons_dir.iterdir():
        if category_dir.is_dir():
            for repo_dir in category_dir.iterdir():
                if repo_dir.is_dir() and addon_name.lower() in repo_dir.name.lower():
                    addon_path = repo_dir
                    break

    if not addon_path:
        error(f"Addon '{addon_name}' not found in {addons_dir}")
        raise typer.Exit(1)

    info(f"Pulling latest from {addon_path}...")

    try:
        import subprocess
        result = subprocess.run(
            ["git", "pull"],
            cwd=addon_path,
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            success(f"Updated {addon_path}")

            # Warn about affected projects
            _warn_affected_projects(addon_path)
        else:
            error(f"Failed to pull: {result.stderr}")
            raise typer.Exit(1)

    except Exception as e:
        error(f"Error pulling: {e}")
        raise typer.Exit(1)


@app.command()
def used_by(addon_path: str = typer.Argument(..., help="Path to addon (e.g., 'enterprise/19.0')")) -> None:
    """Muestra qué proyectos usan un addon compartido específico."""

    # Resolve addon path
    addons_dir = Path.home() / ".odev" / "addons"
    full_addon_path = (addons_dir / addon_path).resolve()

    if not full_addon_path.exists():
        error(f"Addon not found: {full_addon_path}")
        raise typer.Exit(1)

    console.print(f"\n[bold]Projects using {addon_path}:[/bold]\n")

    projects_dir = Path.home() / ".odev" / "projects"
    found_any = False

    for project_dir in projects_dir.iterdir():
        if not project_dir.is_dir():
            continue

        odev_yaml = project_dir / "odev.yaml"
        if not odev_yaml.exists():
            continue

        # Check if this addon is referenced in odev.yaml
        content = odev_yaml.read_text()
        if str(full_addon_path) in content or addon_path in content:
            console.print(f"  ✓ {project_dir.name}")
            found_any = True

    if not found_any:
        info("No projects use this addon")


# Helper functions

def _count_odoo_modules(directory: Path) -> int:
    """Count __manifest__.py files (Odoo modules) in directory."""
    return len(list(directory.rglob("__manifest__.py")))


def _get_git_info(directory: Path) -> str:
    """Get git branch and last commit info."""
    try:
        import subprocess
        result = subprocess.run(
            ["git", "describe", "--all", "--always"],
            cwd=directory,
            capture_output=True,
            text=True,
            timeout=2
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except:
        pass
    return "(not a git repo)"


def _check_git_updates(directory: Path) -> dict:
    """Check if git repo has updates available."""
    try:
        import subprocess

        # Fetch remote updates
        subprocess.run(
            ["git", "fetch"],
            cwd=directory,
            capture_output=True,
            timeout=5
        )

        # Check for divergence
        result = subprocess.run(
            ["git", "status", "-sb"],
            cwd=directory,
            capture_output=True,
            text=True,
            timeout=2
        )

        output = result.stdout.strip()
        if "behind" in output:
            return {
                "has_updates": True,
                "message": f"{output}"
            }

        return {"has_updates": False, "message": ""}
    except:
        return {"has_updates": False, "message": ""}


def _warn_affected_projects(addon_path: Path) -> None:
    """Warn about projects that might be affected by addon update."""
    projects_dir = Path.home() / ".odev" / "projects"
    affected = []

    for project_dir in projects_dir.iterdir():
        if not project_dir.is_dir():
            continue

        odev_yaml = project_dir / "odev.yaml"
        if odev_yaml.exists() and str(addon_path) in odev_yaml.read_text():
            affected.append(project_dir.name)

    if affected:
        warning(f"\n⚠ This addon update affects {len(affected)} project(s):")
        for project in affected:
            console.print(f"    - {project}")
        info("\nRestart affected projects: odev restart")
```

---

## Improvement 1: Auto-Regenerate Config on odev.yaml Changes

### File: `odev/commands/up.py`

**Current Code:**
```python
def up(build: bool = False, watch: bool = False) -> None:
    """Inicia el entorno."""
    contexto = ObtenerContexto()
    rutas = contexto.rutas

    # ... loads values_env and generates config ...

    # Auto-regenerar odoo.conf si el .env es mas reciente
    archivo_odoo_conf = rutas.config_dir / "odoo.conf"
    if not archivo_odoo_conf.exists() or rutas.env_file.stat().st_mtime > archivo_odoo_conf.stat().st_mtime:
        generate_odoo_conf(...)
```

**Proposed Change:**
```python
def up(build: bool = False, watch: bool = False) -> None:
    """Inicia el entorno."""
    contexto = ObtenerContexto()
    rutas = contexto.rutas

    # ... existing code ...

    # Auto-regenerar docker-compose.yml y odoo.conf si odev.yaml es mas reciente
    docker_compose_file = rutas.docker_compose_file
    odev_config_file = rutas.odev_config
    archivo_odoo_conf = rutas.config_dir / "odoo.conf"

    # Check if odev.yaml is newer than generated files
    if odev_config_file.exists():
        odev_mtime = odev_config_file.stat().st_mtime

        # Regenerate docker-compose.yml if needed
        if not docker_compose_file.exists() or odev_mtime > docker_compose_file.stat().st_mtime:
            info("odev.yaml cambió - regenerando docker-compose.yml...")
            docker_compose_file.unlink(missing_ok=True)
            _regenerar_docker_compose(contexto)  # New helper function

        # Regenerate odoo.conf if needed
        if not archivo_odoo_conf.exists() or odev_mtime > archivo_odoo_conf.stat().st_mtime:
            info("odev.yaml cambió - regenerando config/odoo.conf...")
            generate_odoo_conf(...)
```

### File: `odev/core/config.py`

**Add Path Validation:**
```python
from pathlib import Path

class ProjectConfig:
    def __init__(self, ruta_proyecto: Path) -> None:
        """Carga la configuracion del proyecto desde .odev.yaml."""
        self.ruta_archivo = ruta_proyecto / ".odev.yaml"

        if not self.ruta_archivo.exists():
            raise FileNotFoundError(
                f"No se encontro .odev.yaml en {ruta_proyecto}. "
                "Ejecuta 'odev init' para crear un proyecto."
            )

        with open(self.ruta_archivo, encoding="utf-8") as archivo:
            datos_crudos = yaml.safe_load(archivo) or {}

        self.datos = _mezclar_profundo(_CONFIGURACION_POR_DEFECTO.copy(), datos_crudos)

        # NEW: Validate enterprise path if enabled
        if self.enterprise_habilitado:
            self._validar_ruta_enterprise(ruta_proyecto)

    def _validar_ruta_enterprise(self, ruta_proyecto: Path) -> None:
        """Verifica que la ruta enterprise existe."""
        enterprise_path_str = self.datos.get("enterprise", {}).get("path")

        if not enterprise_path_str:
            return

        # Resolve relative paths against project root
        enterprise_path = Path(enterprise_path_str)
        if not enterprise_path.is_absolute():
            enterprise_path = ruta_proyecto / enterprise_path_str

        if not enterprise_path.exists():
            from odev.core.console import warning

            warning(
                f"⚠ Enterprise path no existe: {enterprise_path}\n"
                f"  Para clonar, ejecuta:\n"
                f"    git clone --branch 19.0 https://github.com/odoo/enterprise.git {enterprise_path}"
            )
```

---

## Improvement 2: Generate odoo.conf with Enterprise addons_path

### File: `odev/core/config.py`

**Current Code:**
```python
def generate_odoo_conf(
    config_dir: Path,
    addon_mounts: list[dict],
    enterprise_enabled: bool = False,
) -> None:
    """Genera config/odoo.conf."""

    addon_paths = [m["container_path"] for m in addon_mounts]
    # BUG: Doesn't append enterprise even if enabled!

    context = {
        "addons_path": ",".join(addon_paths),
        # ... other vars ...
    }

    # Render template...
```

**Proposed Fix:**
```python
def generate_odoo_conf(
    config_dir: Path,
    addon_mounts: list[dict],
    enterprise_enabled: bool = False,
    enterprise_container_path: str = "/mnt/enterprise-addons",
) -> None:
    """Genera config/odoo.conf con soporte para enterprise."""

    addon_paths = [m["container_path"] for m in addon_mounts]

    # FIXED: Append enterprise if enabled
    if enterprise_enabled:
        addon_paths.append(enterprise_container_path)

    context = {
        "addons_path": ",".join(addon_paths),
        "enterprise_enabled": enterprise_enabled,
        # ... other vars ...
    }

    # Render template...
    odoo_conf_file = config_dir / "odoo.conf"
    odoo_conf_file.write_text(rendered_content, encoding="utf-8")
```

**Update Call Site (in up.py):**
```python
# In odev/commands/up.py - update the generate_odoo_conf call:

generate_odoo_conf(
    rutas.config_dir,
    addon_mounts=addon_mounts,
    enterprise_enabled=bool(contexto.config and contexto.config.enterprise_habilitado),
    enterprise_container_path="/mnt/enterprise-addons",
)
```

---

## Improvement 3: Add watch/sync for Enterprise in docker-compose

### File: `templates/project/docker-compose.yml.j2`

**Current Code:**
```jinja
{% if enterprise_enabled %}
      - {{ enterprise_path | default('./enterprise') }}:/mnt/enterprise-addons
{% endif %}
      - ./logs:/var/log/odoo
    environment: ...
    entrypoint: ...
    develop:
      watch:
{% for mount in addon_mounts %}
        - action: sync
          path: {{ mount.host_path }}
          target: {{ mount.container_path }}
{% endfor %}
    # BUG: No watch rule for enterprise!
```

**Proposed Fix:**
```jinja
{% if enterprise_enabled %}
      - {{ enterprise_path | default('./enterprise') }}:/mnt/enterprise-addons
{% endif %}
      - ./logs:/var/log/odoo
    environment: ...
    entrypoint: ...
    develop:
      watch:
{% for mount in addon_mounts %}
        - action: sync
          path: {{ mount.host_path }}
          target: {{ mount.container_path }}
          ignore:
            - __pycache__
            - .git
{% endfor %}
{% if enterprise_enabled %}
        - action: sync
          path: {{ enterprise_path | default('./enterprise') }}
          target: /mnt/enterprise-addons
          ignore:
            - __pycache__
            - .git
{% endif %}
```

---

## Improvement 4: New Command `odev sync-config`

### File: `odev/commands/sync_config.py` (NEW)

```python
"""Comando `odev sync-config` — regenera archivos de configuracion.

Util cuando editas manualmente odev.yaml y necesitas que los cambios
se reflejen en docker-compose.yml, odoo.conf, y entrypoint.sh sin
reiniciar los contenedores.
"""

import typer
from pathlib import Path

from odev.core.console import console, error, info, success
from odev.core.context import ObtenerContexto
from odev.core.config import generate_odoo_conf, construir_addon_mounts


def sync_config() -> None:
    """Regenera archivos de configuracion desde odev.yaml.

    Util cuando cambias:
    - enterprise.enabled / enterprise.path
    - paths.addons
    - odoo.version o database.image

    No reinicia contenedores; ejecuta `odev restart` manualmente
    para aplicar cambios.
    """

    try:
        contexto = ObtenerContexto()
    except FileNotFoundError as e:
        error(f"Proyecto no encontrado: {e}")
        raise typer.Exit(1)

    rutas = contexto.rutas
    config = contexto.config

    info("Regenerando archivos de configuracion...")

    # 1. Remove stale files to force regeneration
    files_to_remove = [
        rutas.docker_compose_file,
        rutas.config_dir / "odoo.conf",
        rutas.config_dir / "entrypoint.sh",
    ]

    for file in files_to_remove:
        if file.exists():
            file.unlink()
            info(f"  Removido: {file.name}")

    # 2. Regenerate docker-compose.yml
    info("  Generando docker-compose.yml...")
    _generar_docker_compose(contexto)

    # 3. Regenerate odoo.conf
    info("  Generando odoo.conf...")
    valores_env = _cargar_env(contexto)
    addon_mounts = construir_addon_mounts(
        config.rutas_addons,
        rutas.config_dir,
    )
    enterprise_enabled = bool(config and config.enterprise_habilitado)

    generate_odoo_conf(
        rutas.config_dir,
        addon_mounts=addon_mounts,
        enterprise_enabled=enterprise_enabled,
    )

    # 4. Regenerate entrypoint.sh
    info("  Generando entrypoint.sh...")
    _generar_entrypoint(contexto)

    success("Archivos de configuracion sincronizados.")
    info("Reinicia Odoo para aplicar cambios: odev restart")


# Helper functions (extracted from existing code)
def _generar_docker_compose(contexto) -> None:
    """Generate docker-compose.yml from template."""
    # ... existing logic from up.py ...
    pass


def _cargar_env(contexto) -> dict:
    """Load .env values."""
    # ... existing logic ...
    pass


def _generar_entrypoint(contexto) -> None:
    """Generate entrypoint.sh."""
    # ... existing logic ...
    pass
```

**Register in `odev/commands/__init__.py`:**
```python
from .sync_config import sync_config

@app.command()
def sync_config() -> None:
    """Regenera archivos de configuracion desde odev.yaml."""
    from odev.commands.sync_config import sync_config as sync_config_impl
    sync_config_impl()
```

---

## Improvement 5: Better Enterprise Detection in `odev adopt`

### File: `odev/core/detect.py`

**Current Code:**
```python
class RepoLayout:
    def __init__(self, ruta: Path):
        self.ruta = ruta
        self.tipo = self._detectar_tipo()
        self.rutas_addons = self._detectar_addons()
        self.tiene_enterprise = self._detectar_enterprise()  # BUG: Not working in external mode

    def _detectar_enterprise(self) -> bool:
        """Detecta si el proyecto tiene un directorio enterprise."""
        return (self.ruta / "enterprise").is_dir()
```

**Proposed Fix:**
```python
    def _detectar_enterprise(self) -> bool:
        """Detecta si el proyecto tiene enterprise."""
        # Check in project root
        if (self.ruta / "enterprise").is_dir():
            return True

        # Check in working_dir if external mode
        working_dir_env = os.getenv("ODEV_WORKING_DIR")
        if working_dir_env:
            working_dir = Path(working_dir_env)
            if (working_dir / "enterprise").is_dir():
                return True

        # Check in odev.yaml if it exists
        odev_yaml = self.ruta / ".odev.yaml"
        if odev_yaml.exists():
            try:
                with open(odev_yaml) as f:
                    config_data = yaml.safe_load(f) or {}
                    return config_data.get("enterprise", {}).get("enabled", False)
            except:
                pass

        return False
```

---

## Testing Checklist

### Test 1: Shared Enterprise Setup
```bash
# 1. Clone enterprise once
mkdir -p ~/.odev/addons
git clone --branch 19.0 https://github.com/odoo/enterprise.git ~/.odev/addons/enterprise

# 2. Create project and enable enterprise
odev init test-project --no-interactive
cd ~/.odev/projects/test-project

# 3. Edit odev.yaml
# Set: enterprise.enabled: true, path: /home/user/.odev/addons/enterprise

# 4. Run sync-config
odev sync-config

# 5. Verify docker-compose.yml has enterprise mount
grep -A 2 "enterprise-addons" docker-compose.yml

# 6. Verify odoo.conf has enterprise in addons_path
grep "addons_path" config/odoo.conf | grep enterprise

# 7. Start and verify modules load
odev up
```

### Test 2: Hot-Reload for Enterprise
```bash
# 1. Edit a file in ~/.odev/addons/enterprise/account_accountant/models/
# 2. Should auto-sync to /mnt/enterprise-addons in container
# 3. Odoo should reload automatically
```

### Test 3: Path Validation
```bash
# Edit odev.yaml with non-existent path:
# enterprise.path: /nonexistent/path

# Run odev up
# Should error with helpful message about cloning enterprise
```

---

## Discussion Points for Maintainers

1. **Backwards Compatibility:** These changes are non-breaking. Projects without enterprise should work as before.

2. **File Hash vs mtime:** Should we use file content hash instead of mtime for regeneration detection? More robust but slower.

3. **Optional Enterprise:** Should enterprise be loaded only on explicit install, or auto-available when enabled?

4. **Multi-Version Support:** Should odev support multiple enterprise versions (one per Odoo version)?

5. **Auto-Clone:** Should `odev up` automatically clone enterprise if `enabled: true` and path doesn't exist?

---

## Performance Impact

- ✅ **No negative impact:** File checks are fast (<1ms)
- ✅ **Faster for users:** No more manual docker-compose.yml deletion
- ✅ **Better DX:** Clearer error messages for missing enterprise paths

---

## References

- Odoo Enterprise GitHub: https://github.com/odoo/enterprise
- Docker Compose watch feature: https://docs.docker.com/compose/file-watch/
- Jinja2 templates: https://jinja.palletsprojects.com/

