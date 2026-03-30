"""Comando `odev addons` — gestionar addons compartidos.

Permite listar, actualizar y gestionar addons compartidos entre proyectos.
"""

import typer
from pathlib import Path
from typing import Optional

from odev.core.console import console, info, success, warning, error
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
    try:
        shared = [p for p in addon_paths if not Path(p).is_relative_to(contexto.rutas.root)]
        if shared:
            console.print("\n[bold]SHARED ADDONS:[/bold]")
            for path in shared:
                num_modules = _count_odoo_modules(Path(path))
                console.print(f"  🔗 {path} ({num_modules} modules)")
    except ValueError:
        # is_relative_to might fail on some systems; skip shared addon detection
        pass


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
    try:
        shared_paths = [
            p for p in addon_paths
            if not Path(p).is_relative_to(contexto.rutas.root)
        ]
    except ValueError:
        shared_paths = []

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

    if projects_dir.exists():
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

    if projects_dir.exists():
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
