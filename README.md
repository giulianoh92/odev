# odev

**CLI toolkit for Docker-based Odoo development environments.**

![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)
![License MIT](https://img.shields.io/badge/license-MIT-green)
![PyPI](https://img.shields.io/badge/pypi-odev-orange)

## What is odev?

odev is a command-line toolkit that provides a complete, Docker-based Odoo development environment. Each project is fully independent with its own configuration, database, ports, and Docker Compose stack. Install odev once globally, then create as many isolated Odoo projects as you need.

## Quick Start

```bash
pip install git+https://github.com/giulianoh92/odev.git
odev init my-project
cd my-project
odev up
# Open http://localhost:8069
```

The `init` command runs an interactive wizard that lets you choose the Odoo version (17.0, 18.0, 19.0), database credentials, ports, and optional features like Enterprise addons, pgweb, debugpy, and GitHub Actions CI.

For non-interactive setup with sensible defaults:

```bash
odev init my-project --no-interactive
```

## Features

- **One-command setup** -- `odev init` scaffolds an entire project with Docker Compose, Odoo config, `.env`, `.gitignore`, pre-commit hooks, and optional CI pipeline
- **Hot-reload** -- Odoo runs in dev mode; XML, QWeb, and JS changes are picked up automatically
- **Database snapshots** -- Save and restore database state at any point with `odev db snapshot` / `odev db restore`
- **Module scaffolding** -- `odev scaffold` generates a complete Odoo module skeleton (models, views, security, tests)
- **Multi-project support** -- Automatic port detection ensures multiple projects can run simultaneously without conflicts
- **Interactive TUI** -- Terminal dashboard with live service status, log streaming, and keyboard shortcuts
- **Load external backups** -- Import Odoo.sh or Database Manager `.zip` backups with automatic neutralization
- **Data anonymization** -- Strip personal data from production database copies for safe development
- **Project context generation** -- Generate a `PROJECT_CONTEXT.md` with module analysis for AI coding assistants
- **Legacy migration** -- Migrate from the old `odoo-dev-env` layout to independent projects
- **Environment diagnostics** -- `odev doctor` checks Docker, Compose, ports, config files, and version compatibility
- **Self-update** -- `odev self-update` upgrades to the latest version via pip
- **Shared addon management** -- Manage enterprise and shared addons across multiple projects with `odev addons`
- **Config regeneration** -- `odev sync-config` regenerates docker-compose.yml and odoo.conf without restarting containers

## Commands Reference

### Top-level Commands

| Command | Description |
|---------|-------------|
| `odev init [name]` | Create a new Odoo project (interactive wizard or `--no-interactive`) |
| `odev up` | Start the development environment (`--build` to rebuild, `--watch` for watch mode) |
| `odev down` | Stop and remove containers (`-v` to also remove volumes) |
| `odev restart` | Restart the Odoo web container |
| `odev status` | Show service status table (name, state, health, ports) |
| `odev logs [service]` | Follow service logs (`web`, `db`, or `all`; `--tail`, `--no-follow`) |
| `odev shell` | Open an interactive bash shell inside the Odoo container |
| `odev test <module>` | Run tests for a module (or `all`; `--log-level` to control verbosity) |
| `odev scaffold <name>` | Create a new Odoo module from the bundled template |
| `odev addon-install <module>` | Install a module for the first time and restart |
| `odev update <module>` | Upgrade a module and restart |
| `odev reset-db` | Destroy database and volumes, then restart with a fresh environment |
| `odev load-backup <path>` | Load an Odoo.sh / Database Manager backup (`.zip`; `--no-neutralize`) |
| `odev context` | Generate `PROJECT_CONTEXT.md` from module analysis |
| `odev tui` | Launch the interactive TUI dashboard |
| `odev migrate` | Migrate a legacy `odoo-dev-env` project to the new format |
| `odev sync-config` | Regenerate docker-compose.yml and odoo.conf from odev.yaml without restarting |
| `odev doctor` | Diagnose the development environment and report problems |
| `odev self-update` | Update odev to the latest version |

### Database Subcommands (`odev db`)

| Command | Description |
|---------|-------------|
| `odev db snapshot <name>` | Create a database snapshot (pg_dump in custom format) |
| `odev db restore <name>` | Restore database from a snapshot (by name or prefix) |
| `odev db list` | List all available snapshots with date and size |
| `odev db anonymize` | Anonymize personal data (names, emails, phones) and reset passwords |

### Addon Subcommands (`odev addons`)

| Command | Description |
|---------|-------------|
| `odev addons list` | List all addons used by the current project |
| `odev addons list --global` | List all shared addons available in `~/.odev/addons/` |
| `odev addons check-updates` | Check for updates in shared addons used by the project |
| `odev addons pull <addon>` | Update a shared addon from its remote repository |
| `odev addons used-by <addon>` | Show which projects use a specific shared addon |

## Project Structure

Running `odev init my-project` generates the following directory tree:

```
my-project/
├── addons/                  # Your custom Odoo modules (tracked in git)
├── config/
│   └── odoo.conf            # Auto-generated from .env (gitignored)
├── enterprise/              # Enterprise addons (optional, gitignored)
├── snapshots/               # Database snapshots (gitignored)
├── logs/                    # Odoo log files (gitignored)
├── docs/                    # Documentation and SDD artifacts
├── docker-compose.yml       # Docker services (Odoo + PostgreSQL + pgweb)
├── entrypoint.sh            # Container entrypoint script
├── .odev.yaml               # Project configuration for odev
├── .env                     # Environment variables (gitignored)
├── .env.example             # Shareable environment template
├── .gitignore               # Pre-configured ignores
├── .pre-commit-config.yaml  # Pre-commit hooks (ruff, etc.)
├── pyproject.toml           # Project tooling config
├── CLAUDE.md                # Instructions for AI coding assistants
└── .github/
    └── workflows/
        └── ci.yml           # GitHub Actions CI (optional)
```

## Configuration

### .odev.yaml

The project configuration file that odev uses to detect and manage the project:

```yaml
odev_min_version: "0.1.0"

odoo:
  version: "19.0"
  image: "odoo:19"

database:
  image: "pgvector/pgvector:pg16"

enterprise:
  enabled: false
  path: "./enterprise"

services:
  pgweb: true

project:
  name: "my-project"
  description: ""
```

### .env

Environment variables that control the Docker stack. Created by `odev init` and gitignored (secrets stay local). Share `.env.example` with your team instead.

Key variables:

| Variable | Default | Purpose |
|----------|---------|---------|
| `ODOO_VERSION` | `19.0` | Odoo version |
| `ODOO_IMAGE_TAG` | `19` | Docker image tag for Odoo |
| `DB_IMAGE_TAG` | `16` | PostgreSQL version (via pgvector image) |
| `WEB_PORT` | `8069` | Odoo web port |
| `PGWEB_PORT` | `8081` | pgweb port |
| `DB_NAME` | `odoo_db` | Database name |
| `DB_USER` | `odoo` | Database user |
| `LOAD_LANGUAGE` | `en_US` | Language to auto-install |
| `WITHOUT_DEMO` | `all` | Skip demo data (`all` = skip, empty = load) |
| `DEBUGPY` | `False` | Enable remote debugger on port 5678 |

## Multi-Project Support

odev automatically detects available ports when creating a new project. If port 8069 is already in use (by another odev project, for example), `odev init` will suggest the next available port set:

```
Project A: Odoo on 8069, pgweb on 8081, DB on 5432
Project B: Odoo on 8070, pgweb on 8082, DB on 5433
Project C: Odoo on 8071, pgweb on 8083, DB on 5434
```

Each project has its own Docker Compose stack with isolated containers and volumes. Just run `odev up` in each project directory.

## Database Management

### Snapshots

Save and restore database state at any point during development:

```bash
# Save the current database state
odev db snapshot clean-install

# Make changes, experiment, break things...

# Restore to the saved state
odev db restore clean-install

# List all available snapshots
odev db list
```

Snapshots are saved as PostgreSQL custom-format dumps in the `snapshots/` directory with timestamps, so you can have multiple snapshots with the same prefix.

### Load External Backups

Import an Odoo.sh or Database Manager backup (`.zip` containing `dump.sql` or `dump.dump` with optional `filestore/`):

```bash
odev load-backup /path/to/backup.zip
```

This command:
1. Extracts the backup archive
2. Stops the web service to free database connections
3. Drops and recreates the database
4. Restores the SQL dump (supports both plain SQL and custom format)
5. Copies the filestore into the Odoo data volume (if present)
6. Neutralizes the database (disables crons, mail servers, etc.)
7. Resets admin credentials to `admin` / `admin`
8. Restarts all services

Use `--no-neutralize` to skip the neutralization step.

### Anonymization

Strip personal data from a production database copy for safe development:

```bash
odev db anonymize
```

Replaces names, emails, phone numbers, and addresses with fake data. Resets all user passwords to `admin`.

### Reset Database

Start completely fresh by destroying the database and all Docker volumes:

```bash
odev reset-db
```

This runs `docker compose down -v` followed by `docker compose up -d`.

## Shared Addon Management

odev supports managing enterprise and shared addons across multiple projects. All shared addons are stored in a single location (`~/.odev/addons/`) and referenced by projects via the `addons_paths` configuration in `.odev.yaml`.

### Setup Shared Enterprise

Clone the Odoo enterprise repository once to a shared location:

```bash
mkdir -p ~/.odev/addons/enterprise/19.0
git clone --branch 19.0 https://github.com/odoo/enterprise.git ~/.odev/addons/enterprise/19.0
```

### Use in Your Project

In your project's `.odev.yaml`, reference the shared addon path:

```yaml
addons_paths:
  - "./addons"                                    # Project-specific
  - "~/.odev/addons/enterprise/19.0"             # Shared enterprise
```

Then run `odev up` as usual. odev automatically:
- Mounts the shared addon path in Docker
- Includes it in Odoo's `addons_path` configuration
- Sets up hot-reload for code changes
- Validates that the path exists (with helpful error message if missing)

### Discover and Manage Shared Addons

```bash
# See what addons this project uses
odev addons list

# See all shared addons available globally
odev addons list --global

# Check which projects use a specific shared addon
odev addons used-by enterprise/19.0

# Update a shared addon (affects all projects using it)
odev addons pull enterprise
```

For comprehensive documentation on shared addon management, see [~/.odev/addons/README.md](~/.odev/addons/README.md).

## Module Development

### Create a New Module

```bash
odev scaffold my_module
```

This creates `addons/my_module/` with a complete Odoo module structure:

```
addons/my_module/
├── __init__.py
├── __manifest__.py
├── models/
│   ├── __init__.py
│   └── my_module.py          # Example model with fields
├── views/
│   └── my_module_views.xml   # List + form views, action, menu item
├── security/
│   └── ir.model.access.csv   # Access control list
└── tests/
    ├── __init__.py
    └── test_my_module.py     # Example TransactionCase test
```

### Development Workflow

```bash
# 1. Create the module skeleton
odev scaffold my_module

# 2. Edit models, views, security rules...

# 3. Install the module for the first time
odev addon-install my_module

# 4. After making changes to Python models or data files
odev update my_module

# 5. Run tests
odev test my_module

# 6. Generate project context for AI assistants
odev context
```

XML and JS changes are picked up automatically thanks to Odoo's dev mode with hot-reload.

### Testing

```bash
# Test a specific module
odev test my_module

# Test with a specific log level
odev test my_module --log-level debug

# Run all tests (can take a long time)
odev test all
```

## Migration from odoo-dev-env

If you have an existing project using the old `odoo-dev-env` layout (where the tool repository IS the project), you can migrate to the new format:

```bash
# 1. Install odev globally
pip install git+https://github.com/giulianoh92/odev.git

# 2. Navigate to your existing project
cd /path/to/your-odoo-dev-env-project

# 3. Run the migration
odev migrate
```

The `migrate` command will:
- Create `.odev.yaml` from your existing `.env` configuration
- Update `.gitignore` to track `addons/` (instead of ignoring it)
- Generate missing files (`.env.example`, `CLAUDE.md`, etc.)
- Create required directories (`docs/`, `snapshots/`, `logs/`) with `.gitkeep`

After migration, review the changes with `git diff`, then commit:

```bash
git add .odev.yaml addons/
git commit -m "feat: migrate to independent project format"
```

## TUI Dashboard

Launch the interactive terminal dashboard:

```bash
odev tui
```

The TUI provides three panels:
- **Status panel** -- Live service status (auto-refreshes) showing container state, health, and ports
- **Actions bar** -- Quick reference for keyboard shortcuts
- **Log viewer** -- Streaming Odoo logs in real time

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `U` | Start services (docker compose up) |
| `D` | Stop services (docker compose down) |
| `R` | Restart the Odoo web container |
| `S` | Open a bash shell in the Odoo container |
| `C` | Generate PROJECT_CONTEXT.md |
| `Q` | Quit the TUI |

## Environment Diagnostics

Run `odev doctor` to check your environment:

```bash
odev doctor
```

It verifies:
- Docker is installed and running
- Docker Compose v2 is available
- Python version is 3.10+
- Project is detected (PROJECT, LEGACY, or NONE mode)
- `.env` file exists
- `docker-compose.yml` exists
- `config/odoo.conf` exists
- `addons/` directory and module count
- Configured ports are available (not in use by other processes)
- CLI version is compatible with the project's `odev_min_version`

Example output:

```
Diagnostico del entorno odev
========================================

  [OK]   Docker instalado (Docker version 27.x.x)
  [OK]   Docker Compose v2 disponible
  [OK]   Python 3.12.x
  [OK]   Proyecto detectado: my-project (modo: project)
  [OK]   .env existe
  [OK]   docker-compose.yml existe
  [OK]   config/odoo.conf existe
  [INFO] addons/ tiene 3 modulo(s)
  [OK]   Puerto 8069 (Odoo) disponible
  [OK]   Puerto 8081 (pgweb) disponible
  [OK]   odev version 0.1.0 (minimo requerido: 0.1.0)

Todas las verificaciones pasaron correctamente.
```

## Installation

### With pip

```bash
pip install git+https://github.com/giulianoh92/odev.git
```

### With pipx (isolated environment)

```bash
pipx install git+https://github.com/giulianoh92/odev.git
```

### For contributors (editable install)

```bash
git clone https://github.com/giulianoh92/odev.git
cd odev
pip install -e ".[dev]"
```

## Requirements

- **Python 3.10+** (3.12 recommended)
- **Docker** with **Docker Compose v2** (Docker Desktop or `docker-compose-plugin`)
- A terminal that supports ANSI colors (for the TUI and Rich output)

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Install dev dependencies: `pip install -e ".[dev]"`
4. Make your changes
5. Run linting: `ruff check src/ && ruff format --check src/`
6. Run tests: `pytest`
7. Submit a pull request

## License

MIT
