# Politica de Versionado

`odev` usa [SemVer 2.0](https://semver.org/spec/v2.0.0.html). Reglas simples:

## Formato `MAJOR.MINOR.PATCH`

| Bump | Cuando | Ejemplo |
| ---- | ------ | ------- |
| **PATCH** (`0.3.0 -> 0.3.1`) | Bugfix sin cambio de comportamiento publico. Refactor interno. Docs. Tests. | `[fix]`, `[refactor]`, `[docs]`, `[test]`, `[chore]` |
| **MINOR** (`0.3.0 -> 0.4.0`) | Funcionalidad nueva. Flag nuevo. Comando nuevo. Cambio retrocompatible. | `[feat]` |
| **MAJOR** (`0.x.y -> 1.0.0`) | Breaking change: signatura CLI, formato `odev.yaml`, exit codes, drop de version Odoo soportada. | `[feat!]` o nota `BREAKING` en cuerpo |

### Pre-1.0 (estado actual)

Mientras la version siga en `0.y.z`, la API CLI se considera **inestable**. Breaking changes acumulan en MINOR (`0.3.0 -> 0.4.0`), no fuerzan MAJOR. El primer `1.0.0` se publica cuando el set de comandos publicos se considera estable.

## Flujo de release

1. Commits siguen formato `[type] scope: descripcion` (existente en `git log`). Tipos: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`.
2. **Cada release** actualiza en un solo commit `[chore] release: X.Y.Z`:
   - `pyproject.toml` -> `version = "X.Y.Z"`
   - `CHANGELOG.md` -> nueva seccion `## [X.Y.Z] - YYYY-MM-DD` con cambios agrupados (`Agregado` / `Corregido` / `Cambiado` / `Eliminado`).
3. **Tag git**: `git tag vX.Y.Z && git push origin vX.Y.Z`.
4. **No** se taggea cada commit. **No** se hace bump por cada PR. Bump al cerrar un grupo de cambios significativos o antes de instalar en una workstation.

## Quien decide el bump

- PATCH: cualquier commit del tipo correspondiente. Bump opcional, puede acumular hasta proxima release.
- MINOR: al menos un `[feat]` desde el ultimo tag => bump obligatorio antes de tag.
- MAJOR: requiere nota explicita en commit body (`BREAKING CHANGE: ...`) y mencion en CHANGELOG.

## Fuente de verdad

`pyproject.toml#version` es la unica fuente de verdad de la version instalable. `README.md` puede contener ejemplos ilustrativos (`0.1.0` en output simulado) — esos son ejemplos, no version actual.
