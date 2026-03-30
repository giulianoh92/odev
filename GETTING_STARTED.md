# Getting Started with odev

**A Complete Beginner's Guide to Docker-Based Odoo Development**

If you're new to odev, this guide will take you from zero to a fully working Odoo development environment in about 15 minutes. No prior Docker or Odoo knowledge required.

---

## Table of Contents

1. [What is odev?](#what-is-odev)
2. [Installation](#installation)
3. [Creating Your First Project](#creating-your-first-project)
4. [Starting and Stopping Services](#starting-and-stopping-services)
5. [Checking Status and Viewing Logs](#checking-status-and-viewing-logs)
6. [Creating Your First Module](#creating-your-first-module)
7. [Basic Development Workflow](#basic-development-workflow)
8. [Database Management](#database-management)
9. [Using Enterprise Addons](#using-enterprise-addons)
10. [Multiple Projects](#multiple-projects)
11. [Troubleshooting](#troubleshooting)

---

## What is odev?

**odev is a command-line toolkit that gives you a complete Odoo development environment inside Docker.**

Instead of installing Odoo manually on your computer (which is complicated), odev handles all the Docker complexity for you. Think of it like:

```
Traditional way:    Install Python → Install PostgreSQL → Install Odoo → Configure everything
odev way:          odev init my-project → odev up
```

Key benefits:
- ✅ **Isolated projects** — Each project has its own database, ports, and containers
- ✅ **One-command setup** — No complex configuration
- ✅ **Hot-reload** — Edit code, refresh browser, changes appear instantly
- ✅ **Database snapshots** — Save/restore database state
- ✅ **Multiple projects** — Run 3+ Odoo projects simultaneously without conflicts
- ✅ **Pre-configured** — Git, pre-commit hooks, CI pipeline included

---

## Installation

### Prerequisites

Before installing odev, you need two things on your computer:

1. **Python 3.10+** (3.12 recommended)
   ```bash
   python3 --version
   ```
   If you don't have it, install from [python.org](https://www.python.org)

2. **Docker** with Docker Compose v2
   - **Mac/Windows:** Install [Docker Desktop](https://www.docker.com/products/docker-desktop)
   - **Linux:** Follow [Docker Engine installation](https://docs.docker.com/engine/install/) + [Docker Compose Plugin](https://docs.docker.com/compose/install/linux/)

   Verify:
   ```bash
   docker --version
   docker compose version
   ```

### Install odev

Choose one method:

**Option 1: Simple Install (recommended)**
```bash
pip install git+https://github.com/giulianoh92/odev.git
```

**Option 2: Isolated Install (safest)**
```bash
pipx install git+https://github.com/giulianoh92/odev.git
```

**Option 3: For Contributors (development)**
```bash
git clone https://github.com/giulianoh92/odev.git
cd odev
pip install -e ".[dev]"
```

### Verify Installation

```bash
odev --version
odev --help
```

You should see the version number and a list of commands.

---

## Creating Your First Project

### Step 1: Interactive Setup

The easiest way is to let odev ask you questions:

```bash
odev init my-first-project
```

You'll be asked:

```
Odoo version? [17.0 / 18.0 / 19.0]: 19.0
Database name? [odoo_db]: my_database
Web port? [8069]: 8069
Enable pgweb (database browser)? [y/n]: y
Enable Enterprise addons? [y/n]: n
Enable debugpy (remote debugger)? [y/n]: n
```

Press Enter to accept defaults, or type your choice.

### Step 2: Navigate to Your Project

```bash
cd my-first-project
```

Inside, you'll see:

```
my-first-project/
├── addons/                  ← Your custom modules go here
├── config/
│   └── odoo.conf            ← Auto-generated (edit odev.yaml instead)
├── docker-compose.yml       ← Auto-generated (edit odev.yaml instead)
├── entrypoint.sh            ← Auto-generated
├── .odev.yaml               ← Project configuration (EDIT THIS)
├── .env                     ← Environment variables (keep private)
├── .env.example             ← Share this with your team
├── .gitignore               ← Git ignore rules
├── .pre-commit-config.yaml  ← Code quality checks
├── pyproject.toml           ← Python tooling
├── CLAUDE.md                ← Instructions for AI coding assistants
└── .github/
    └── workflows/
        └── ci.yml           ← Optional CI pipeline
```

### Step 3 (Optional): Non-Interactive Setup

If you want sensible defaults with no questions:

```bash
odev init my-project --no-interactive
```

---

## Starting and Stopping Services

### Start Your Development Environment

```bash
odev up
```

This will:
1. Build Docker images (first time only, takes ~2-3 minutes)
2. Create PostgreSQL database
3. Start Odoo web server
4. Set up pgweb (if enabled)
5. Download required Python packages

After startup, you'll see:

```
✓ Odoo web: http://localhost:8069
✓ pgweb: http://localhost:8081 (optional)
```

Open your browser to `http://localhost:8069` and log in with:
- **Username:** admin
- **Password:** admin

### Stop Everything

```bash
odev down
```

This stops all containers but keeps your database.

### Restart Without Rebuilding

```bash
odev restart
```

Useful when you want to restart Odoo but keep the database running.

---

## Checking Status and Viewing Logs

### View Service Status

```bash
odev status
```

Shows:

```
Service     State       Health     Ports
─────────────────────────────────────────
web         running     healthy    8069
db          running     healthy    5432
pgweb       running     healthy    8081
```

### View Live Logs

Follow Odoo logs in real time:

```bash
odev logs
```

Follow database logs:

```bash
odev logs db
```

Follow all services:

```bash
odev logs all
```

Press `Ctrl+C` to stop following.

### Interactive Dashboard

For a full visual dashboard:

```bash
odev tui
```

Shows status, logs, and quick keyboard shortcuts.

---

## Creating Your First Module

### Generate Module Skeleton

```bash
odev scaffold my_module
```

This creates:

```
addons/my_module/
├── __init__.py
├── __manifest__.py          ← Module metadata
├── models/
│   ├── __init__.py
│   └── my_module.py         ← Your first model (database table)
├── views/
│   └── my_module_views.xml  ← List/Form/Search views
├── security/
│   └── ir.model.access.csv  ← User permissions
└── tests/
    ├── __init__.py
    └── test_my_module.py    ← Unit tests
```

### Install the Module

```bash
odev addon-install my_module
```

Then:
1. Open Odoo in browser
2. Go to **Apps** menu (top left)
3. Search for **My Module**
4. Click **Install**

### Update After Code Changes

After editing Python models or XML data:

```bash
odev update my_module
```

Then refresh your browser.

### For XML/QWeb/JS Changes

Just refresh your browser — odev's hot-reload picks them up automatically.

### Run Tests

```bash
odev test my_module
```

All tests should pass.

---

## Basic Development Workflow

Here's how you'll work day-to-day:

```bash
# 1. Start the environment
odev up

# 2. Edit files in addons/my_module/
#    • Python models: edits take effect after odev update
#    • XML views: edits show after browser refresh
#    • JS: edits show after browser refresh

# 3. Test your changes
odev test my_module

# 4. View logs if something breaks
odev logs

# 5. When done
odev down
```

### Typical Edits

**Edit a Python Model:**
```python
# addons/my_module/models/my_module.py
class MyModel(models.Model):
    _name = "my.module"

    name = fields.Char("Name")
    active = fields.Boolean(default=True)
```

Then run:
```bash
odev update my_module
```

**Edit a View:**
```xml
<!-- addons/my_module/views/my_module_views.xml -->
<form string="My Form">
    <field name="name"/>
    <field name="active"/>
</form>
```

Just refresh your browser.

---

## Database Management

### Save Database Snapshots

At any point, save your database state:

```bash
odev db snapshot clean-install
```

You can have multiple snapshots:

```bash
odev db snapshot after-import
odev db snapshot before-testing
```

### Restore from Snapshot

```bash
odev db restore clean-install
```

Instantly revert to that exact state.

### List Snapshots

```bash
odev db list
```

Shows all saved snapshots with timestamps and sizes.

### Load Production Database

To test with real data from production:

```bash
odev load-backup /path/to/backup.zip
```

odev will:
1. Extract the backup
2. Replace your database
3. Remove sensitive data (cron jobs, mail servers, reset passwords)
4. Set admin password to `admin`

Use `--no-neutralize` if you want to skip the data cleanup.

### Start Fresh

To delete everything and start over:

```bash
odev reset-db
```

---

## Using Enterprise Addons

If you have access to Odoo Enterprise, you can use enterprise modules.

### One-Time Setup

1. **Clone enterprise to a shared location:**

```bash
# Create shared addons directory
mkdir -p ~/.odev/addons/enterprise/19.0

# Clone (you need GitHub access)
git clone --branch 19.0 https://github.com/odoo/enterprise.git ~/.odev/addons/enterprise/19.0
```

2. **Configure your project to use it:**

Edit your project's `.odev.yaml`:

```yaml
enterprise:
  enabled: true
  path: ~/.odev/addons/enterprise/19.0

addons_paths:
  - ./addons                           # Your custom modules
  - ~/.odev/addons/enterprise/19.0     # Shared enterprise
```

3. **Regenerate config and restart:**

```bash
odev sync-config
odev restart
```

### Using in Your Project

Once configured, enterprise modules are automatically available:

```bash
# Start your project
odev up

# In Odoo, go to Apps and search for enterprise modules
# (e.g., "Accounting", "Web Grid View", etc.)
```

### Managing Shared Enterprise

If you have multiple projects using the same enterprise clone:

```bash
# See which of your projects use enterprise
odev addons used-by enterprise/19.0

# Update enterprise (affects all projects using it)
cd ~/.odev/addons/enterprise/19.0
git pull

# Restart each project
odev restart
```

---

## Multiple Projects

One of odev's superpowers is running multiple projects simultaneously.

### Create Project A

```bash
odev init project-a
cd project-a
odev up
# Runs on port 8069
```

### Create Project B (in another terminal)

```bash
odev init project-b
cd project-b
odev up
# Automatically assigned port 8070 (since 8069 is taken)
```

Each project has:
- ✅ Independent database
- ✅ Independent ports (8069, 8070, 8071...)
- ✅ Independent Docker containers
- ✅ Independent volumes (no disk conflicts)

### View All Projects

```bash
# In project-a
odev status

# In project-b
odev status
```

Each shows its own ports.

### Shared Addons Across Projects

If Project A and Project B both need enterprise:

```yaml
# Both projects' .odev.yaml
addons_paths:
  - ./addons
  - ~/.odev/addons/enterprise/19.0  # Same path, both projects use it
```

No duplication, saves disk space.

---

## Configuration

### Project Config (.odev.yaml)

This is the **single source of truth** for your project:

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
  description: "My first Odoo project"
```

After editing this file, regenerate configs:

```bash
odev sync-config
odev restart
```

### Environment Variables (.env)

Auto-generated after `odev init`. Customize:

| Variable | Example | Purpose |
|----------|---------|---------|
| `ODOO_VERSION` | `19.0` | Odoo version |
| `WEB_PORT` | `8069` | Web server port |
| `DB_NAME` | `odoo_db` | Database name |
| `DB_USER` | `odoo` | Database user |
| `LOAD_LANGUAGE` | `en_US` | Default language |
| `WITHOUT_DEMO` | `all` | Skip demo data |
| `DEBUGPY` | `False` | Enable remote debugger |

**Keep `.env` private** — share `.env.example` with your team instead.

---

## Troubleshooting

### Odoo Won't Start

**Problem:** `odev up` takes forever or fails

**Solution:**
```bash
# Check what's happening
odev logs

# Look for ERROR in the logs
# Common causes: port in use, insufficient disk space, Docker not running
```

**Check Docker is running:**
```bash
docker ps
```

If that fails, Docker isn't running. Start Docker Desktop or the Docker daemon.

### Port Already in Use

**Problem:** `Port 8069 already in use`

**Solution:**

Either:
1. Use a different port (odev will suggest one)
2. Stop the other project:
   ```bash
   cd /path/to/other-project
   odev down
   ```

### Database Won't Connect

**Problem:** `could not translate host name "db" to address`

**Solution:**

Containers can't talk to each other. Restart everything:

```bash
odev down -v
odev up
```

The `-v` flag deletes all volumes (database), so you start fresh.

### Module Not Installing

**Problem:** `Module not found` or `failed to load module`

**Solution:**

```bash
# 1. Check syntax in __manifest__.py
# 2. Verify file is in addons/my_module/__manifest__.py
# 3. Restart
odev restart

# 4. In Odoo, go to Settings → Technical → Modules, search for it
```

### Hot-Reload Not Working

**Problem:** Changed a file but Odoo didn't pick it up

**Solution:**

- **XML/JS:** Just refresh your browser
- **Python models:** Run `odev update my_module` then refresh
- **__manifest__.py:** Run `odev restart`

### Can't Connect to Database Browser

**Problem:** Can't access pgweb on port 8081

**Solution:**

1. Check if it's enabled:
   ```bash
   odev status
   ```
   If pgweb isn't listed, enable it in `.odev.yaml`:
   ```yaml
   services:
     pgweb: true
   ```

2. Regenerate and restart:
   ```bash
   odev sync-config
   odev restart
   ```

### Disk Space Running Out

**Problem:** Docker containers taking up lots of space

**Solution:**

Database snapshots and Docker images use space. Clean up:

```bash
# Remove all snapshots
rm snapshots/*.dump

# List all snapshots
odev db list

# Remove specific snapshot
rm snapshots/snapshot-name-*.dump
```

---

## Quick Reference

### Most Common Commands

| Command | What It Does |
|---------|------------|
| `odev up` | Start everything |
| `odev down` | Stop everything |
| `odev restart` | Restart Odoo |
| `odev status` | Show service status |
| `odev logs` | View live logs |
| `odev scaffold my_module` | Create new module |
| `odev addon-install my_module` | Install module first time |
| `odev update my_module` | Upgrade module |
| `odev test my_module` | Run tests |
| `odev db snapshot name` | Save database |
| `odev db restore name` | Load database |
| `odev tui` | Interactive dashboard |

### Environment Diagnostics

If something's wrong, run:

```bash
odev doctor
```

It checks:
- Docker is installed
- Docker Compose v2 is available
- Python version
- Project configuration
- Port availability
- Version compatibility

---

## Next Steps

Now that you know the basics:

1. **Read the full README.md** for advanced features
2. **Create your first module** with `odev scaffold my_app`
3. **Install the module** with `odev addon-install my_app`
4. **Edit Python models** and run `odev update my_app`
5. **Create views** in XML
6. **Write tests** in `tests/test_*.py`
7. **Run tests** with `odev test my_app`

---

## Getting Help

### Commands That Help You Learn

```bash
odev --help                    # List all commands
odev up --help                 # Help for a specific command
odev doctor                     # Diagnose problems
```

### Documentation

- **README.md** — Full feature reference
- **~/.odev/addons/README.md** — Shared addons protocol
- **Project CLAUDE.md** — AI assistant instructions

### Common Questions

**Q: Can I use odev with Windows?**
A: Yes, install Docker Desktop. Works the same as Mac/Linux.

**Q: Can I have 10 projects running at once?**
A: Yes, but each needs unique ports. odev auto-assigns them.

**Q: Does odev work with Odoo 17, 18, 19?**
A: Yes. Set `version` in `.odev.yaml`.

**Q: Can I use it for production?**
A: No, odev is for development only. Use Odoo.sh or managed hosting for production.

**Q: Do I need to know Docker?**
A: No, odev hides all Docker complexity. You just use `odev` commands.

---

## Congratulations! 🎉

You now know everything you need to start developing with Odoo using odev.

**Next time you're stuck:**
1. Run `odev doctor` to diagnose
2. Check the troubleshooting section above
3. Read the full README.md
4. Ask for help with the exact error message

Happy coding!
