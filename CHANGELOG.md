# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-03-19

### Added

- Initial release of odev as an installable pip package
- 18 top-level CLI commands:
  - `init` -- Interactive project wizard (or `--no-interactive` for defaults)
  - `up` -- Start Docker Compose environment (`--build`, `--watch`)
  - `down` -- Stop and remove containers (`-v` to remove volumes)
  - `restart` -- Restart the Odoo web container
  - `status` -- Service status table with Rich formatting
  - `logs` -- Follow service logs (`--tail`, `--no-follow`)
  - `shell` -- Interactive bash shell in the Odoo container
  - `test` -- Run Odoo module tests (`--log-level`)
  - `scaffold` -- Create a new module from the bundled template
  - `addon-install` -- Install a module for the first time
  - `update` -- Upgrade a module and restart
  - `reset-db` -- Destroy database and volumes, fresh start
  - `load-backup` -- Import Odoo.sh / Database Manager backups (`.zip`)
  - `context` -- Generate PROJECT_CONTEXT.md from module analysis
  - `tui` -- Interactive terminal dashboard (Textual)
  - `migrate` -- Migrate legacy odoo-dev-env projects to new format
  - `doctor` -- Environment diagnostics (Docker, Compose, ports, config)
  - `self-update` -- Upgrade odev via pip
- 4 database subcommands (`odev db`):
  - `snapshot` -- Create a database snapshot (pg_dump custom format)
  - `restore` -- Restore database from a snapshot
  - `list` -- List available snapshots with date and size
  - `anonymize` -- Replace personal data with fake values, reset passwords
- Interactive TUI dashboard with:
  - Live service status panel (auto-refresh)
  - Streaming log viewer
  - Keyboard shortcuts for common actions (U/D/R/S/C/Q)
- Project detection with three modes: PROJECT, LEGACY, NONE
- Multi-project support with automatic port allocation
- Jinja2-based project scaffolding (docker-compose.yml, .env, odoo.conf, etc.)
- Module template with models, views, security, and tests
- Odoo version support: 19.0, 18.0, 17.0
- PostgreSQL with pgvector support (pg16 for Odoo 18/19, pg15 for Odoo 17)
- Optional Enterprise addons, pgweb, debugpy, and GitHub Actions CI
- Auto-regeneration of odoo.conf when .env changes
- Backup loading with automatic neutralization and admin credential reset
- Pre-commit configuration generation (ruff)
- CLAUDE.md generation for AI coding assistant integration
