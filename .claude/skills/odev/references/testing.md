# The one-run test protocol

The default failure pattern: run `odev test` in summary mode, hit a failure,
re-run with `--verbose` to read the traceback, apply a fix, then re-run the
whole battery to confirm. On a project with a non-trivial test suite that is
three full runs at 5-10 minutes each — and two of the three are avoidable.

## The protocol

1. **Always run once, capturing both machine-readable and raw output:**

   ```
   odev test <modules> --json --save-log <scratchpad>/odev-test-<modules>-<timestamp>.log
   ```

   To test what the diff touched, replace `<modules>` with `--changed`
   (see "Scoping a run to the diff" below) instead of building the CSV by
   hand.

2. **Diagnose from the JSON. Never re-run with `--verbose` to see a
   traceback.** The `failures[]` array carries, per failure: `class`,
   `method`, `kind` (`FAIL` / `ERROR` / `LOADING_ERROR`), `message`, and
   `traceback` — the complete captured traceback: file, line number, the
   failing expression and the exception.

3. **Read the saved log only when `parse_failed` is `true`.** That is the
   one case where the JSON cannot tell you anything about the run, and the
   raw log is the fallback.

4. **Check `process_exit_code` when the result looks wrong for no reason
   visible in `failures[]`.** It carries the raw code the Odoo process
   exited with — `0` on every normal run, including one with test
   failures, since Odoo itself exits 0 in that case. A nonzero value here
   (137 from the OOM killer, 139 from a segfault) means the process died
   outright rather than a test failing cleanly, and no traceback will
   explain it.

5. **After fixing, re-run only what failed — never the whole battery.**
   - One test: `odev test <module>:<Class>.<method>`
   - Several: the comma-OR form on `--tags` —
     `odev test <module> --tags ":<ClassA>.<test_x>,:<ClassB>.<test_y>"`

6. **Run the full battery one final time only when the fix could plausibly
   regress something outside its blast radius.** Not reflexively, on every
   fix. Before a PR, `odev test --changed --base <branch> --with-dependents`
   is usually that blast radius.

## Scoping a run to the diff: `--changed`

`odev test --changed [--base <ref>] [--with-dependents]` (MCP: `odev_test`
with `changed=True`, `base`, `with_dependents`) selects the modules and runs
them through exactly the same path as `odev test m1,m2`: same Odoo command,
same `--tags`, same zero-test warning and discovery lint.

- **Changed files:** everything that differs between `merge-base(<base>,
  HEAD)` and the working tree (committed, staged, unstaged), plus untracked
  files git does not ignore. `--base` defaults to `HEAD`: only uncommitted
  work. Each file maps to its nearest ancestor with `__manifest__.py`.
  Changed git submodules are traversed the same way, against the commit the
  superproject recorded at the base, recursively.
- **`--with-dependents`** adds installed modules that depend *directly* on
  the selection (not transitive ones). It queries the DB, so the stack must
  be up.
- **Skipped with a `WARN` on stderr** (in `warnings` for MCP): modules
  outside the project's addons path, deleted modules, and submodules that
  cannot be traversed (no checkout, base commit missing — run the suggested
  `git -C <path> fetch` —, removed, or git failing inside it). Read these: a skipped module was not
  tested.
- **The selection is announced on stderr**; under `--json` the payload adds
  `modules`. Report it with the counts.
- **Empty selection exits 0 without running Odoo.** The JSON has zero
  counters, `modules: []` and `process_exit_code: null`. That is "nothing
  to test", not a passing run.
- **Errors:** module and `--changed` together, neither, `--base`/
  `--with-dependents` without `--changed`, or a `--base` that does not
  resolve: exit 2. git missing, not a git repo, a broken HEAD (the ref exists
  but does not resolve to a commit, or a detached HEAD whose commit is missing
  — an unborn branch compares against the empty tree), or the DB down for
  `--with-dependents`: exit 3.

## Why this is safe — the facts, not just the shortcut

- **`--save-log` writes every raw line Odoo emits, unconditionally.** The
  `echo` parameter — the one `--verbose` sets — only controls whether a line
  is *also* re-emitted live to stdout; the write to the save-log file
  happens regardless of `echo`. `--verbose` adds **nothing** to the saved
  file that a plain `--json --save-log` run does not already capture.
- **`--verbose` is mutually exclusive with `--json`/`--summary`/`--failures`
  (exit 2)**, because the raw stream is never parsed. The "quick `--verbose`
  re-run" is never a cheap add-on to the first run — it is always a second
  full battery, end to end.
- **The comma-OR semantics of `--tags`** is exactly the right tool for
  re-running N specific failed tests in a single pass, once you target it
  explicitly instead of letting odev auto-generate `/module` prefixes.

**Caveat on `--tags ":Class.method"`:** a spec with no tag component
defaults to the `standard` tag, which matches nearly every test, including
`post_install` ones. A test explicitly excluded from `standard` needs its
own tag named explicitly, or a narrow re-run using only `:Class.method` will
silently skip it.

## Cost comparison

| Pattern | Runs | Rough cost |
|---|---|---|
| Summary → `--verbose` → full re-run | 3 full batteries | 15-30 min |
| One `--json --save-log` → N narrow re-runs → optional full re-run | 1 full + N narrow (seconds each) + at most 1 optional full | 5-10 min (+ optional 5-10 min) |

## `--tags` semantics

Odoo **ORs** comma-separated `--test-tags` specs; it never intersects them.
An include with no tag component defaults to `standard`, which matches
nearly everything.

`--tags` **replaces** the auto-generated `/module` prefixes entirely — it
does not append to them. `odev test sale --tags foo` emits
`--test-tags foo` (not `--test-tags /sale,foo`): `-u sale` already scopes
which modules run, so the tag expression alone filters exactly within them.
Concatenating a prefix with a user expression would OR them and run the
entire module regardless of the filter.

The `module:Class.method` shorthand and `--tags` cannot be combined (exit
2): both define the test filter, and Odoo would OR them instead of
intersecting — exactly the over-broad match this design avoids. Pick one.

## The zero-test warning and the discovery lint

A run that executes zero tests exits 0 with `failed: 0, errors: 0` —
indistinguishable from success unless something says otherwise.

**Zero-test warning.** When a run's `total` is 0, odev writes a warning to
stderr naming the effective module/tag filter used. It is a warning, not an
error, and never changes the exit code or the JSON: zero tests is legitimate
for a module that genuinely has none, and `odev test all` must keep working
on a project with untested modules. Always check `total` in the JSON output,
not just `failed`/`errors`.

**Discovery lint.** Before launching, odev compares each target module's
`tests/test_*.py` files against what its `tests/__init__.py` actually
imports (parsed with `ast`, not regex, to handle grouped imports and
conditionals) and warns on stderr for every orphaned file.

**The underlying rule.** Odoo only discovers test modules that are
**imported** in the addon's `tests/__init__.py` — `get_test_modules` uses
`inspect.getmembers(mod, inspect.ismodule)`, and a submodule becomes an
attribute of the package only once something imports it. A `test_*.py` file
that nobody imports contributes zero tests, silently.

Other causes of a zero-test run the same warning covers: a misspelled module
name that still passes addons-path validation, and a `--tags` expression
that matches nothing.
