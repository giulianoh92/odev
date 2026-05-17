# odev — Roadmap de Desarrollo

> **Fecha:** 2026-05-17
> **Version base:** 0.4.0
> **Metodologia:** auditoria multi-axis (bugs/quality, feature gaps Odoo workflow, integrations/AI/IDE/MCP, architecture/UX) con 4 sub-agents en paralelo.
> **Orden:** alto a bajo ROI. Tier 1 (urgente) → Tier 4 (estrategico/opcional).
> **Convenciones effort:** XS &lt; 1h · S 1-4h · M 4h-1d · L 1-3d · XL &gt; 1 semana.

---

## Resumen ejecutivo

| Estado | Item |
|--------|------|
| Bugs criticos descubiertos | **6** (incluye 1 path traversal SECURITY) |
| Code smells / tech debt | **10** |
| Gaps de funcionalidad Odoo workflow | **10 areas**, 15 features priorizadas |
| Integraciones AI/IDE/MCP propuestas | **10 top + MCP server detallado** |
| Problemas arquitectonicos | **10** + 15 quick wins |
| Releases sugeridas | 0.4.1 (fix) · 0.5.0 (agent-friendly) · 0.6.0 (Odoo.sh + TUI) · 1.0.0 |

**Fortalezas existentes que NO romper:** separacion `commands/` ↔ `core/`, resolver unificado, `DockerCompose.from_context()` factory, `_helpers.py` plumbing, output via `core/console.py`.

**Direccion estrategica:** convertir odev en la **plataforma agent-friendly canonica para Odoo dev**, manteniendo TUI/UX para humanos. Tres pilares:
1. **Sin friction para IAs** (JSON output, MCP server, model-info)
2. **Cobertura ciclo completo Odoo** (local → Odoo.sh → self-hosted)
3. **Robustez en edge cases** (security, concurrency, multi-host)

---

## Tier 1 — CRITICAL (release inmediato, 0.4.1 patch)

ROI altisimo. Effort total ~1-2 dias. Bugs latentes con impacto serio (security, data loss, Python compat).

### 1.1 Bugs criticos

| # | Bug | Severity | Effort | File:line |
|---|-----|----------|--------|-----------|
| B1 | **Path traversal en `load-backup`** — `zf.extractall()` sin filtrar entries. ZIP malicioso con `../../.ssh/authorized_keys` puede escribir fuera del temp dir | 🔴 SECURITY | S | `commands/load_backup.py:111` |
| B2 | **TOCTOU race en `registry._escribir_fcntl`** — `.exists()` antes de `open()`, gap previo al flock. Bajo concurrencia → `FileNotFoundError` o truncate | 🔴 DATA | XS | `core/registry.py:150-151` |
| B3 | **Dump cargado completo en RAM** — `archivo_dump.read_bytes()`. Dumps prod 5-20 GB → OOM | 🔴 PROD | M | `commands/load_backup.py:138` |
| B4 | **`asyncio.get_event_loop()` deprecado** — RuntimeError potencial en Python 3.12+. TUI crashea silencioso | 🟠 COMPAT | XS | `tui/log_viewer.py:159` |
| B5 | **`except Exception: pass` en `reset_db`** — silencia errores fatales 150s sin diagnostico | 🟠 UX | XS | `commands/reset_db.py:128` |
| B6 | **`fcntl` import top-level sin guard Windows** — `ModuleNotFoundError` al primer uso de Registry en Windows | 🟡 PLATFORM | XS | `core/registry.py:11` |

### 1.2 Seguridad

| # | Issue | Fix |
|---|-------|-----|
| S1 | `.env` generado sin `chmod 0600` (passwords legibles por otros usuarios) | `init.py` + `adopt.py`: `Path.chmod(0o600)` post-write |
| S2 | SQL injection parcial en `load_backup.py:120-128` (regex permite `.` `-` en `nombre_bd` sin quoting) | Restringir regex a `^[a-zA-Z_][a-zA-Z0-9_]*$` o usar `psycopg2.sql.Identifier` |
| S3 | `migrate._generar_env_example()` puede committear secrets si user hace `git add .env.example` | Agregar comentario warning + chmod 0600 |

### 1.3 Quick wins UX (≤ 1h cada uno)

Lista pre-priorizada del audit arquitectonico:

| # | Quick win | Effort |
|---|-----------|--------|
| Q1 | `--debug` global en `main.py` callback → `logging.basicConfig(level=DEBUG)` | XS |
| Q2 | `Registry._leer()` backup automatico en YAML invalido (`.bak` + error visible) | XS |
| Q3 | Exponer subgrupos (`db`, `projects`, `enterprise`) en `odev --help` raiz | XS |
| Q4 | `up.py` no imprimir URL pgweb si `services.pgweb=false` | XS |
| Q5 | `down.py`/`reset-db`/`load-backup` agregar `--dry-run` flag | S |
| Q6 | `odev doctor` ordenar checks por criticidad (Docker → Compose → proyecto → .env → puertos) | XS |
| Q7 | `preflight.py` mensaje error con hint `odev --project {owner} down` | XS |
| Q8 | `LogViewer` usar `asyncio.get_running_loop()` (cubre B4) | XS |
| Q9 | `StatusPanel` TUI: agregar columna "Puertos" + colorear estado | S |
| Q10 | Mover lista `PORT_KEYS` a `core/ports.py` (dedupe `up.py` + `doctor.py`) | XS |

**Total Tier 1:** ~6-8 commits, release 0.4.1 PATCH.

---

## Tier 2 — TRANSFORMATIONAL (release 0.5.0 — "Agent-Ready")

Effort: 2-3 semanas. Impact: cada usuario AI-asistido (Claude Code/Cursor/agentes) gana 10x productividad con Odoo.

### 2.1 Enabler critico

| # | Feature | Effort | Por que primero |
|---|---------|--------|-----------------|
| E1 | **`DockerCompose.exec_capture(service, cmd) -> (stdout, stderr, rc)`** | S | Bloquea TODO: MCP server, `--json` outputs, `odev py`/`sql` parseable. Hoy solo hay `exec_cmd` (interactive) y `exec_cmd_stream` (Popen passthrough). |

### 2.2 Agent-friendly API (JSON output + introspeccion)

| # | Feature | Effort | ROI | Descripcion |
|---|---------|--------|-----|-------------|
| F1 | `odev status --json` | XS | 🔴 | Output estructurado del status (services, ports, health) |
| F2 | `odev doctor --json` | S | 🔴 | Diagnostico estructurado (checks list con name/status/message) |
| F3 | `odev logs --json` | S | 🟠 | Lineas como `{ts, service, level, message}` |
| F4 | `odev modules --json` | S | 🔴 | Listado completo modulos: technical_name, installed, depends, version, source_module |
| F5 | `odev model-info <model> [--live]` | M | 🔴 | Fields + constraints + inherits. AST estatico o consulta ORM via `odev py` |
| F6 | `odev grep <pattern> [--type model\|view\|qweb]` | S | 🟠 | Wrapper `rg` con conocimiento de addons-paths + `--json` |
| F7 | `odev context --json --quiet` | S | 🟠 | Hoy solo genera Markdown. JSON parseable + sin output decorativo |
| F8 | `odev py` descarta banner Odoo automaticamente | XS | 🟠 | Hoy el agente necesita `\| tail -n 1`. Limpiar internamente |
| F9 | `odev sql` retornar rows estructuradas (no ASCII table) | S | 🟠 | Modo `--json` con `[{col1, col2}, ...]` |
| F10 | Exit codes documentados en `--help` de TODOS los commands | XS | 🟡 | Estandarizar (0/1/2/3 ya en `test`) |

### 2.3 MCP Server (`odev mcp serve`)

**Effort: L** (3-5 dias). **Impact: 🔴 maximo**.

Expone odev como MCP server. Claude Code/Cursor lo consumen sin parsear stdout.

**Tools a exponer:**
```
odev_status, odev_shell, odev_sql, odev_py, odev_test, odev_logs,
odev_doctor, odev_model_info, odev_modules
```

**Resources:**
```
odev://project/context    → PROJECT_CONTEXT.md (auto-refresh si stale)
odev://project/config     → odev.yaml parseado
odev://db/schema          → pg_dump --schema-only
odev://modules/{name}/manifest  → manifest parseado
```

**Prompts pre-armados:**
```
diagnose-failing-test, explain-module, generate-migration
```

**Entry points:**
```bash
odev mcp serve --transport stdio                # Claude Code
odev mcp serve --transport http --port 3333     # Cursor / otros
```

**Config Claude Code generada automaticamente por `odev ide-setup --claude`.**

### 2.4 Claude Code / IDE integration

| # | Feature | Effort | Descripcion |
|---|---------|--------|-------------|
| I1 | `odev ide-setup --claude` | M | Genera `.claude/settings.json` + `.claude/hooks/odev-context.sh` (auto-refresh PROJECT_CONTEXT.md vía PostToolUse hook) + permissions allow list para `Bash(odev *)` |
| I2 | `odev ide-setup --vscode` | M | `.vscode/{tasks,launch,settings,extensions}.json`. Tasks up/down/test, launch.json debugpy attach, ruff config, recomendaciones pylint-odoo |
| I3 | `odev ide-setup --cursor` | S | Idem VSCode + `.cursorrules` con contexto Odoo |
| I4 | Skill custom `/odev:diagnose` | S | Run `odev test --json` → analiza failures → sugiere fix |
| I5 | Skill custom `/odev:scaffold` | S | Lee PROJECT_CONTEXT → sugiere nombre tecnico + depends → invoca scaffold |

### 2.5 Module dev experience (loop iterativo)

| # | Feature | Effort | ROI | Descripcion |
|---|---------|--------|-----|-------------|
| D1 | `odev test --watch` | M | 🔴 | watchdog/inotify re-run al guardar `.py`/`.xml`. Diff de resultados |
| D2 | `odev test --coverage` | M | 🔴 | HTML coverage.py de modulo |
| D3 | `odev test <mod>:<Class>.<method>` shorthand | S | 🔴 | Hoy hay `--tags /mod:Class.method`. Sintaxis corta. |
| D4 | `odev lint <mod>` | S | 🔴 | flake8 + pylint-odoo dentro del container |
| D5 | `odev assets debug` | S | 🟠 | Toggle `assets_debug_mode` via SQL + restart |
| D6 | `odev scaffold --wizard\|--report\|--controller` | M | 🟠 | Templates para wizards, reports QWeb, controllers HTTP |

### 2.6 DB tooling para developers

| # | Feature | Effort | ROI |
|---|---------|--------|-----|
| DB1 | `odev db multi` — clone/switch/list multiples DBs por stack | M | 🔴 |
| DB2 | `odev db diff <snap1> <snap2>` — diff schema | M | 🟠 |
| DB3 | `odev db size` — tabla de tamanos por tabla/indice | S | 🟡 |
| DB4 | `odev anonymize` extender (full GDPR: users, account, sale, stock) | M | 🟠 |

**Release 0.5.0:** ~25 features, foco agent-friendliness + DX loop.

---

## Tier 3 — STRATEGIC (release 0.6.0 — "Odoo.sh + TUI Pro")

Effort: 3-5 semanas. Cubre el segundo pilar (ciclo completo Odoo) y consolida arquitectura.

### 3.1 Odoo.sh integration (gap completo)

Hoy: solo `load-backup` acepta ZIP de Odoo.sh. Resto del flujo = manual.

| # | Feature | Effort | ROI |
|---|---------|--------|-----|
| SH1 | `odev sh db pull <branch>` — download backup + load-backup auto | M | 🔴 |
| SH2 | `odev sh ssh <branch>` — SSH directo al build | M | 🔴 |
| SH3 | `odev sh logs <branch>` — stream logs build remoto | S | 🔴 |
| SH4 | `odev sh status` — list builds (running, errored, success) | S | 🟠 |
| SH5 | `odev sh test <branch>` — trigger CI + poll resultado | M | 🟠 |
| SH6 | `odev sh modules diff <branch>` — comparar local vs build remoto | M | 🟡 |
| SH7 | `odev sh sync` — push branch + trigger build | M | 🟡 |

**Prereq:** API token Odoo.sh en `~/.odev/credentials.yaml` (chmod 0600).

### 3.2 SSH remoto general (self-hosted + Odoo.sh)

| # | Feature | Effort | ROI |
|---|---------|--------|-----|
| T1 | `odev tunnel <host> [--db --web --debugpy]` — port forwards SSH | S | 🔴 |
| T2 | `odev profile remote <host>` — py-spy SSH + flamegraph local | M | 🟠 |
| T3 | `odev logs remote <host>` — wrap `ssh ... tail -f` con filtros | S | 🟡 |

### 3.3 Multi-proyecto orchestration

| # | Feature | Effort | ROI |
|---|---------|--------|-----|
| M1 | `odev projects status` — tabla global (containers, version, ports, DB size) | M | 🔴 |
| M2 | `odev projects up/down --all` + `--group <workspace>` | S | 🟠 |
| M3 | Concepto workspace (agrupar proyectos relacionados) | M | 🟡 |
| M4 | Conflict puerto: sugerir libre + auto-reasignar con prompt | S | 🟠 |

### 3.4 Lifecycle commands faltantes

| # | Feature | Effort | ROI |
|---|---------|--------|-----|
| L1 | `odev destroy` — down -v + remove registry + opcional borrar dir | S | 🔴 |
| L2 | `odev rename <old> <new>` — rename atomico (registry + .env + odev.yaml + regen) | M | 🟠 |
| L3 | `odev clone <source> <dest>` — fork registry entry con nuevos puertos | M | 🟠 |
| L4 | `odev archive` — down + marcar archived + liberar puertos | S | 🟡 |

### 3.5 TUI killer features

Estado actual: status panel + log viewer + project info + paleta + 7 keybindings.

| # | Feature | Effort | Impact |
|---|---------|--------|--------|
| TUI1 | **Search/filter en LogViewer** (vim `/`, regex/substring) | M | 🔴 |
| TUI2 | Notificaciones OS al terminar tests largos (`notify-send` / AppleScript) | S | 🔴 |
| TUI3 | Test runner integrado en pane separado con stream parser | M | 🟠 |
| TUI4 | CPU/RAM por contenedor en status panel (`docker stats --no-stream --format json`) | S | 🟠 |
| TUI5 | Profile switcher (cambiar de proyecto sin salir TUI) | M | 🟠 |
| TUI6 | Multi-pane real con splitter ajustable | M | 🟡 |
| TUI7 | Keybindings vim-like (`j/k/gg/G/f`) | S | 🟡 |

### 3.6 Refactors arquitectonicos

| # | Refactor | Effort | ROI |
|---|----------|--------|-----|
| R1 | Extraer Jinja2 factory compartida (`core/templates.py`) | XS | 🟠 |
| R2 | Unificar `PORT_KEYS` constante (dedupe up.py + doctor.py) — ya en Tier 1 Q10 | — | — |
| R3 | Migrar `doctor.py` a `resolver_proyecto()` unificado (elimina 7 calls a `detect_mode`) | M | 🟠 |
| R4 | Exponer `Registry.buscar_por_puerto(int) -> str \| None` (cierra violacion encapsulacion en `preflight`) | XS | 🟠 |
| R5 | Mover `_ejecutar_registry_gc_y_backfill` a `Registry.backfill_ports()` | S | 🟡 |
| R6 | Split `doctor.py` (549 LOC god file) en `core/diagnostics/{checks,formatting}.py` | L | 🟡 |
| R7 | Eliminar global mutable `_nombre_proyecto` en `main.py` → `typer.Context(obj=State)` | M | 🟡 |
| R8 | Deprecar `core/compat.detect_mode()` (duplica resolver) | M | 🟡 |
| R9 | Eliminar import `from odev.commands.context import context` en `tui/app.py` (inversion dependencia) | S | 🟡 |
| R10 | `init.py` (573 LOC): extraer logica a `core/init_engine.py` (testeable sin Typer) | L | 🟡 |

### 3.7 Observability local

| # | Feature | Effort | ROI |
|---|---------|--------|-----|
| O1 | `odev slow-queries [--threshold=100ms]` — parsear pg log + asociar a modulo via `application_name` | S | 🔴 |
| O2 | `odev perf <modulo>` — run tests con cProfile + HTML | M | 🟠 |
| O3 | Sentry integration (template `.env` + DSN) | M | 🟡 |

**Release 0.6.0:** ~30 features, foco Odoo.sh + TUI + refactors arquitectonicos.

---

## Tier 4 — LONG TAIL (post-1.0, opcional)

Effort: meses. Impact: usuarios advanced o nichos.

### 4.1 Self-hosted production

| # | Feature | Effort | ROI |
|---|---------|--------|-----|
| P1 | `odev deploy` — rsync compose + systemd a remote | XL | 🟡 |
| P2 | `odev backup schedule` — cron + offsite (S3/Backblaze) | L | 🟠 (clientes) |
| P3 | `odev ssl setup` — certbot + nginx integration | M | 🟡 |
| P4 | `odev monitor` — uptime/RAM/disk/longpolling check via SSH | L | 🟡 |
| P5 | `odev workers set <n>` — editar workers + restart remoto | S | 🟢 |

### 4.2 Asset/frontend dev

| # | Feature | Effort | ROI |
|---|---------|--------|-----|
| A1 | SCSS/JS watch sin rebuild completo | L | 🟡 |
| A2 | OWL devtools integration | L | 🟢 |

### 4.3 Plugin/extension system

| # | Feature | Effort | ROI |
|---|---------|--------|-----|
| X1 | Custom commands del usuario (`~/.odev/plugins/`) | L | 🟡 |
| X2 | Hooks pre/post (`pre-up`, `post-test`) | M | 🟡 |
| X3 | Custom services en docker-compose | M | 🟡 |

### 4.4 Documentation / Discoverability

| # | Feature | Effort | ROI |
|---|---------|--------|-----|
| C1 | Ejemplos inline en `--help` (Typer epilog Rich) | S | 🟠 |
| C2 | `odev cheatsheet` interactivo | S | 🟡 |
| C3 | Manpage (`man odev`) | M | 🟢 |
| C4 | Tutorial integrado paso a paso | L | 🟡 |

### 4.5 CI/CD

| # | Feature | Effort | ROI |
|---|---------|--------|-----|
| CI1 | `odev ci-setup --provider github\|gitlab` — workflow + coverage badge | M | 🟠 |
| CI2 | Pre-commit hooks generator extendido (pylint-odoo, prettier XML) | S | 🟠 |

---

## Casos de uso reales (que se desbloquean)

Estos workflows hoy duelen sin odev. Cada uno mapea a features arriba.

| # | Workflow | Features que lo cubren |
|---|----------|------------------------|
| U1 | "Traer prod a local en 5 minutos" | SH1 (`sh db pull`) + L1 (`destroy` para limpiar) |
| U2 | "Debug issue que solo se reproduce en Odoo.sh" | SH2 + SH3 (`sh ssh + logs`) |
| U3 | "Datos prod sin violar GDPR" | DB4 (`anonymize` full) |
| U4 | "Detectar query lenta" | O1 (`slow-queries`) |
| U5 | "Trabajar multi-ticket en paralelo" | DB1 (`db multi`) |
| U6 | "Iterar rapido sin restart manual" | D1 (`test --watch`) + `up --watch` fixes |
| U7 | "Asegurar tests pasan antes de commit" | CI2 (pre-commit hook que invoca `odev test`) |
| U8 | "Comparar modulos local vs Odoo.sh" | SH6 (`sh modules diff`) |
| U9 | "Iniciar 2 proyectos clientes paralelo" | M4 (auto-reasignar puerto) |
| U10 | "Setup Claude Code en proyecto Odoo" | I1 (`ide-setup --claude`) + MCP server |

---

## Plan de releases sugerido

| Release | Foco | Effort | Tier | Features destacadas |
|---------|------|--------|------|----------------------|
| **0.4.1** | Patch security + quick wins | ~2 dias | T1 | 6 bugs + 3 sec + 10 quick wins |
| **0.5.0** | Agent-Ready | ~3 semanas | T2 | `exec_capture`, JSON output universal, MCP server, `model-info`, IDE setup, test --watch/coverage, `db multi` |
| **0.6.0** | Odoo.sh + TUI Pro + refactors | ~4 semanas | T3 | `sh db pull/ssh/logs`, `tunnel`, `projects status`, `destroy/rename/clone`, search en TUI, refactors R1-R5 |
| **0.7.0** | Polish + observability | ~2 semanas | T3 | `slow-queries`, `perf`, `archive`, TUI multi-pane, refactors R6-R10 |
| **1.0.0** | API estable | 1 semana | — | Lock CLI surface, doc completa, manpage, schema migration framework (`sugerir_puertos()` eliminada en 0.5.0) |
| **1.x** | Long tail | meses | T4 | Self-hosted deploy, plugin system, asset dev, CI templates |

---

## Apendice A — Bugs detallados (no urgentes ahora)

| # | Code smell | File:line | Sugerencia |
|---|------------|-----------|------------|
| SM1 | `write_text()`/`read_text()` sin encoding (8+ sitios) | `_wizards.py:209`, `context.py:56`, `regen.py:72`, `config.py:69/154`, `init.py:464`, `scaffold.py:84/86` | Pasar `encoding="utf-8"` explicito |
| SM2 | `except Exception: pass` en `init.py:143` (silencia registry fail) | `init.py:143` | `except (PermissionError, YAMLError) as e: warning(...)` |
| SM3 | `doctor.py:200` doble `(FileNotFoundError, Exception)` redundante | `doctor.py:200` | Quitar `FileNotFoundError` de tupla |
| SM4 | `registry.py:290-315` duplicacion `asignar_puertos` / `_asignar_puertos_bajo_lock` | `core/registry.py` | Refactor a helper privado compartido |
| SM5 | `_wizards.py` sin validar puertos/db_name | `_wizards.py` | Validar puerto 1-65535, db_name regex |
| SM6 | `tui/log_viewer.py:149-153` hard-coded `docker compose` (bypass `DockerCompose`) | `tui/log_viewer.py` | Usar `DockerCompose.logs_stream()` |
| SM7 | `sugerir_puertos()` deprecated pero exportada (race condition siempre) | `core/ports.py` | Eliminado en 0.5.0 ✓ |

## Apendice B — Gaps de tests

- `commands/load_backup.py` — **0 tests**. Comando mas destructivo del CLI.
- `commands/context.py` — sin test file propio. Parser modulos sin cobertura.
- `tui/log_viewer.py` — sin test.
- `test_reset_db.py` — solo 6 tests, no cubre `reset_db()` principal.
- `test_concurrency.py` — solo 2 tests, no cubre TOCTOU `_escribir_fcntl`.
- Mocking excesivo de `DockerCompose` esconde bugs reales — falta integration test con docker real.

## Apendice C — Checklist agent-friendly API (consolidado)

- [ ] `dc.exec_capture()` (enabler)
- [ ] `--json` en `status`, `doctor`, `logs`, `context`, `modules`, `sql`, `model-info`, `grep`
- [ ] Errores SIEMPRE a stderr (algunos hoy van a stdout via Rich)
- [ ] Mensajes error formato `ERROR: <codigo>: <mensaje>`
- [ ] Exit codes documentados en `--help` de cada comando
- [ ] `odev py` strip banner Odoo automatico
- [ ] `odev modules --json`, `model-info`, `grep --json` (no existen hoy)
- [ ] `odev context --quiet --json` (hoy solo Markdown)
- [ ] `odev config --json` (expose odev.yaml parseado)
- [ ] Idempotencia: `up` con `--check`, `install`/`update` con `--check`

---

## Apendice D — Tabla maestra ROI

Top 25 items ordenados estrictamente por ROI (impact/effort):

| Rank | Item | Tier | Impact | Effort | ROI |
|------|------|------|--------|--------|-----|
| 1 | B1 path traversal fix | 1 | SECURITY | S | 🔴🔴🔴 |
| 2 | B4/Q8 asyncio.get_running_loop | 1 | COMPAT | XS | 🔴🔴🔴 |
| 3 | Q1 `--debug` flag global | 1 | DX | XS | 🔴🔴 |
| 4 | Q10 dedupe PORT_KEYS | 1 | refactor | XS | 🔴🔴 |
| 5 | S1 .env chmod 0600 | 1 | SECURITY | XS | 🔴🔴 |
| 6 | E1 `dc.exec_capture()` | 2 | enabler | S | 🔴🔴🔴 |
| 7 | F1 `status --json` | 2 | agent | XS | 🔴🔴🔴 |
| 8 | F4 `modules --json` | 2 | agent | S | 🔴🔴 |
| 9 | F5 `model-info` | 2 | agent | M | 🔴🔴 |
| 10 | D3 `test <mod>:<Class>.<m>` shorthand | 2 | DX | S | 🔴🔴 |
| 11 | D4 `odev lint` | 2 | DX | S | 🔴🔴 |
| 12 | D1 `test --watch` | 2 | DX | M | 🔴🔴 |
| 13 | DB1 `db multi` | 2 | DX | M | 🔴🔴 |
| 14 | I1 `ide-setup --claude` | 2 | integration | M | 🔴🔴 |
| 15 | B3 dump streaming en load-backup | 1 | PROD | M | 🔴🔴 |
| 16 | SH1 `sh db pull` | 3 | Odoo.sh | M | 🔴 |
| 17 | T1 `odev tunnel` | 3 | SSH | S | 🔴 |
| 18 | O1 `slow-queries` | 3 | observability | S | 🔴 |
| 19 | MCP server | 2 | integration | L | 🔴 |
| 20 | M1 `projects status` global | 3 | multi-proyecto | M | 🔴 |
| 21 | TUI1 search/filter logs | 3 | TUI | M | 🔴 |
| 22 | L1 `odev destroy` | 3 | lifecycle | S | 🔴 |
| 23 | SH2 `sh ssh` | 3 | Odoo.sh | M | 🔴 |
| 24 | R3 doctor → resolver unificado | 3 | refactor | M | 🟠 |
| 25 | D2 `test --coverage` | 2 | DX | M | 🟠 |

---

## Conclusiones

1. **Bugs criticos primero** (Tier 1, 0.4.1): security (path traversal), data corruption (TOCTOU), prod (OOM en load-backup). ~2 dias bloqueantes.
2. **Agent-friendly es el mayor unlock** (Tier 2, 0.5.0): JSON output + MCP server transforma odev en plataforma canonica para uso AI-asistido en Odoo. Diferenciador competitivo.
3. **Odoo.sh integration** (Tier 3, 0.6.0) es el feature pedido mas no-trivial: cubre el 50% del workflow Odoo profesional que hoy queda fuera.
4. **TUI search/filter** (TUI1) + **test --watch** (D1) son los quick wins de mayor impacto percibido en uso diario.
5. **Refactors arquitectonicos** (R1-R10) prepara el repo para 1.0.0: eliminar `compat.py`, split `doctor.py`, eliminar global mutable.

**Sugerencia inmediata:** SDD para 0.4.1 patch (bugs T1) en proximas horas; SDD para 0.5.0 agent-ready arrancando esta semana con `exec_capture` como primer milestone.
