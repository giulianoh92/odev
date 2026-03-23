# Plan de Mejoras — Code Review odev

- **Fecha**: 2026-03-23
- **Branch**: `feature/code-review-improvements`
- **Estrategia**: Un commit por fase, flujo SDD por sprint

---

## Items OMITIDOS (y por qué)

| Item | Razón |
|------|-------|
| Remover `admin_passwd` de `odoo.conf.j2` | Breaking change — se implementará en una fase posterior dedicada a migración de configuración. |
| Cambiar defaults en `env.example.j2` | Breaking change — requiere coordinación con usuarios existentes; se implementará después. |

---

## Phase 1 — Seguridad (Sprint 1)

### S1: Fix SQL Injection en `neutralize.py`

- **Archivo**: `src/odev/neutralize.py`
- **Problema**: Se usan f-strings para construir queries SQL (líneas 72, 96-102), lo que abre la puerta a inyección SQL.
- **Solución**: Usar archivos SQL temporales con parámetros o escapar correctamente los valores antes de interpolarlos en las queries.

### S2: Pinnear versiones de imágenes Docker

- **Archivo**: `src/odev/templates/docker-compose.yml.j2` (líneas 91, 104)
- **Problema**: `sosedoff/pgweb` se usa sin tag y `mailhog/mailhog:latest` depende de un tag mutable. Esto puede causar roturas silenciosas cuando las imágenes se actualizan.
- **Solución**: Pinnear ambas imágenes a versiones específicas con digest o tag inmutable.

### S3: Validar `nombre_bd` y `usuario_bd` en `neutralize.py`

- **Archivo**: `src/odev/neutralize.py` (líneas 14-109)
- **Problema**: Los parámetros de nombre de base de datos y usuario no se validan antes de usarse en comandos.
- **Solución**: Validar que solo contengan caracteres alfanuméricos, guiones y underscores.

### S4: Validar `service` en `docker.py exec_cmd`

- **Archivo**: `src/odev/docker.py` (líneas 267-270)
- **Problema**: El parámetro `service` se pasa directamente al comando sin validación.
- **Solución**: Validar que solo contenga caracteres seguros (alfanuméricos, guiones, underscores).

### S5: Validar `project_root` en `docker.py __init__`

- **Archivo**: `src/odev/docker.py` (líneas 46-50)
- **Problema**: `project_root` puede ser `None`, lo que causaría errores no descriptivos aguas abajo.
- **Solución**: Agregar validación temprana con un mensaje de error claro.

---

## Phase 2 — Estabilidad (Sprint 2)

### E1: Fix pytest collection error

- **Archivo**: `src/odev/templates/module/tests/test___module_name__.py`
- **Problema**: pytest colecta este archivo de template como un test real durante la ejecución de la suite de tests, causando errores de colección.
- **Solución**: Renombrar el archivo para que pytest no lo detecte (por ejemplo, usar un prefijo diferente o configurar `collect_ignore`).

### E2: Schema validation para `.odev.yaml`

- **Archivo**: `src/odev/project.py` (líneas 76-79)
- **Problema**: El archivo de configuración `.odev.yaml` se carga sin validación de esquema. Errores de tipeo o campos faltantes producen fallos crípticos.
- **Solución**: Agregar validación con pydantic o jsonschema al momento de cargar la configuración.

### E3: Fix race condition en `registry.py`

- **Archivo**: `src/odev/registry.py` (líneas 137-148)
- **Problema**: `fcntl.flock` se adquiere después de `open()`, lo que crea una ventana de race condition donde dos procesos pueden leer/escribir simultáneamente.
- **Solución**: Reestructurar para adquirir el lock inmediatamente después del open y antes de cualquier lectura/escritura.

### E4: Crear método público en DockerCompose para reemplazar `dc._run()`

- **Archivo**: `src/odev/docker.py`
- **Problema**: Varios comandos acceden al método privado `_run()` de DockerCompose directamente, violando la encapsulación.
- **Solución**: Crear un método público con una interfaz clara que exponga la funcionalidad necesaria.

### E5: Agregar healthchecks a pgweb y mailhog

- **Archivo**: `src/odev/templates/docker-compose.yml.j2` (líneas 90-108)
- **Problema**: Los servicios pgweb y mailhog no tienen healthchecks configurados, lo que dificulta la detección de fallos.
- **Solución**: Agregar healthchecks HTTP apropiados para ambos servicios.

### E6: Hacer puerto debugpy condicional

- **Archivo**: `src/odev/templates/docker-compose.yml.j2` (línea 37)
- **Problema**: El puerto de debugpy se expone siempre, incluso cuando no se necesita depuración.
- **Solución**: Hacer que el mapeo del puerto sea condicional, controlado por una variable de entorno o configuración.

---

## Phase 3 — Mantenibilidad (Sprint 3)

### M1: Extraer wizards compartidos de `init.py` y `adopt.py` a `_wizards.py`

- **Archivos**: `src/odev/commands/init.py`, `src/odev/commands/adopt.py`
- **Problema**: Duplicación masiva de ~500 líneas entre ambos archivos, con lógica de wizards casi idéntica.
- **Solución**: Extraer la lógica compartida a un módulo `_wizards.py` reutilizable.

### M2: Unificar `install.py` y `update.py` en función parametrizada

- **Archivos**: `src/odev/commands/install.py`, `src/odev/commands/update.py`
- **Problema**: Ambos comandos comparten estructura y lógica casi idéntica con mínimas diferencias.
- **Solución**: Crear una función parametrizada que maneje ambos casos, reduciendo la duplicación.

### M3: Estandarizar manejo de errores

- **Archivos**: Múltiples archivos en `src/odev/commands/`
- **Problema**: Mezcla inconsistente de `typer.Exit(code)` y `SystemExit()` para señalar errores.
- **Solución**: Estandarizar en `typer.Exit(code)` en todos los comandos para un manejo de errores consistente.

### M4: Estandarizar confirmaciones

- **Archivos**: Múltiples archivos en `src/odev/commands/`
- **Problema**: Se usan indistintamente `questionary.confirm()` y `typer.confirm()`, creando inconsistencia en la UX.
- **Solución**: Elegir una de las dos opciones y usarla consistentemente en todo el proyecto.

### M5: Agregar logging donde se silencian excepciones

- **Archivos**:
  - `src/odev/detect.py` (línea 220)
  - `src/odev/docker.py` (línea 224)
  - `src/odev/paths.py` (línea 76)
- **Problema**: Hay bloques `except` que silencian excepciones sin ningún tipo de registro, haciendo la depuración muy difícil.
- **Solución**: Agregar `logger.debug()` o `logger.warning()` en cada bloque `except` que actualmente silencia errores.

---

## Phase 4 — Mejoras (Sprint 4)

### J1: Agregar configuración de herramientas en `pyproject.toml`

- **Archivo**: `pyproject.toml`
- **Problema**: Faltan secciones de configuración para herramientas de desarrollo.
- **Solución**: Agregar `[tool.pytest.ini_options]`, `[tool.ruff]` y `[tool.coverage.run]` con configuraciones apropiadas para el proyecto.

### J2: Sección de performance comentada en `odoo.conf.j2`

- **Archivo**: `src/odev/templates/odoo.conf.j2`
- **Problema**: No hay guía de configuración de performance para entornos que lo necesiten.
- **Solución**: Agregar una sección comentada con configuraciones de `workers`, `limits`, `proxy_mode` y documentación inline.

### J3: Mejorar `restart` command

- **Archivo**: `src/odev/commands/restart.py`
- **Problema**: El comando `restart` solo reinicia el servicio 'web', sin opción de elegir otro servicio.
- **Solución**: Aceptar un argumento opcional de servicio para poder reiniciar cualquier contenedor del stack.

### J4: Agregar tests de renderizado de templates Jinja2

- **Archivos**: `tests/` (nuevos archivos)
- **Problema**: No hay tests que verifiquen que los templates Jinja2 se renderizan correctamente con diferentes combinaciones de variables.
- **Solución**: Crear tests parametrizados que validen el renderizado de cada template con distintos contextos.

### J5: Agregar `--service` a `shell` command

- **Archivo**: `src/odev/commands/shell.py`
- **Problema**: El comando `shell` solo abre shell en el contenedor por defecto, sin opción de elegir otro.
- **Solución**: Agregar la opción `--service` para permitir abrir shell en cualquier contenedor del stack.

---

## Progress Tracker

| ID | Item | Phase | Status | Commit |
|----|------|-------|--------|--------|
| S1 | Fix SQL Injection en `neutralize.py` | 1 — Seguridad | ✅ Done | `3d9d827` |
| S2 | Pinnear versiones de imágenes Docker | 1 — Seguridad | ✅ Done | `3d9d827` |
| S3 | Validar `nombre_bd` y `usuario_bd` en `neutralize.py` | 1 — Seguridad | ✅ Done | `3d9d827` |
| S4 | Validar `service` en `docker.py exec_cmd` | 1 — Seguridad | ✅ Done | `3d9d827` |
| S5 | Validar `project_root` en `docker.py __init__` | 1 — Seguridad | ✅ Done | `3d9d827` |
| E1 | Fix pytest collection error | 2 — Estabilidad | ✅ Done | `66bc18f` |
| E2 | Schema validation para `.odev.yaml` | 2 — Estabilidad | ✅ Done | `66bc18f` |
| E3 | Fix race condition en `registry.py` | 2 — Estabilidad | ✅ Done | `66bc18f` |
| E4 | Crear método público en DockerCompose | 2 — Estabilidad | ✅ Done | `66bc18f` |
| E5 | Agregar healthchecks a pgweb y mailhog | 2 — Estabilidad | ✅ Done | `66bc18f` |
| E6 | Hacer puerto debugpy condicional | 2 — Estabilidad | ✅ Done | `66bc18f` |
| M1 | Extraer wizards compartidos a `_wizards.py` | 3 — Mantenibilidad | ✅ Done | `f191c53` |
| M2 | Unificar `install.py` y `update.py` | 3 — Mantenibilidad | ✅ Done | `f191c53` |
| M3 | Estandarizar manejo de errores | 3 — Mantenibilidad | ✅ Done | `f191c53` |
| M4 | Estandarizar confirmaciones | 3 — Mantenibilidad | ⏭️ Skipped | — |
| M5 | Agregar logging en excepciones silenciadas | 3 — Mantenibilidad | ✅ Done | `f191c53` |
| J1 | Configuración de herramientas en `pyproject.toml` | 4 — Mejoras | ✅ Done | `3ccd164` |
| J2 | Sección de performance en `odoo.conf.j2` | 4 — Mejoras | ✅ Done | `3ccd164` |
| J3 | Mejorar `restart` command | 4 — Mejoras | ✅ Done | `3ccd164` |
| J4 | Tests de renderizado de templates Jinja2 | 4 — Mejoras | ✅ Done | `3ccd164` |
| J5 | Agregar `--service` a `shell` command | 4 — Mejoras | ✅ Done | `3ccd164` |

---

## Dependencias

- **Phase 1** no tiene dependencias externas — puede comenzar inmediatamente.
- **Phase 2.E4** debe completarse antes de **Phase 3.M1** — el método público de DockerCompose es necesario para el refactor de wizards.
- **Phase 3.M1** es el refactor más grande (~500 líneas) — no bloquea otras tareas pero requiere esfuerzo significativo.
- **Phase 4** no tiene dependencias con otras fases — puede ejecutarse en paralelo si hay capacidad.

```
Phase 1 (Seguridad)
  └── sin dependencias

Phase 2 (Estabilidad)
  └── E4 ──► Phase 3.M1

Phase 3 (Mantenibilidad)
  └── M1 depende de E4

Phase 4 (Mejoras)
  └── sin dependencias (parallelizable)
```
