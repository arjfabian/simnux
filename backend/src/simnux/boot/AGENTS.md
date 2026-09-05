# Boot Contract (`boot/`)

Refines the root SIMNUX Architecture Contract for this directory. Must not
contradict the root document.

## Role

`boot/` is the composition root: it wires configuration, core, and
infrastructure together and starts the application. It is where objects are
constructed and connected, not where architecture is interpreted.

## Owns

* configuration loading (`config.py`);
* object wiring / factory composition (e.g. `app_factory.py`);
* application lifecycle (startup/shutdown, `lifecycle.py`);
* middleware and top-level route registration (`middleware.py`, `routes.py`)
  insofar as it binds infrastructure to the core.

## Must NOT own

* scenario definitions, filesystem behavior, command semantics, or identity
  rules;
* the `SNXSession`/`SNXShell`/`SNXScenario` relationship itself — it only
  builds and composes those objects;
* simulated Linux user/group logic.

## Relationship to the state ownership matrix

When boot composes a session, it must respect the root ownership matrix: the
`SNXSession` owns shells and dispatch; `SNXShell` owns interaction state;
`SNXScenario` owns the world. Boot is the only place that may construct these
together — but it constructs what the contract describes, not a shortcut that
fuses session and shell state.

## Dependency direction

`boot/` depends on `infrastructure/` and `core/`. Nothing depends on `boot/`;
`core/` and `infrastructure/` must never import `boot/`.

## Invariants

* Wiring follows the documented dependency direction even inside factories.
* A scenario is loaded once per shell/session creation and remains the
  immutable world for that shell.
* Starting identity selection (e.g. first non-`root` scenario user) is a
  composition-time decision; the runtime contract places the resulting acting
  user in shell interaction state, not on the app session.

## Terminology

* **composition root** — this directory; the single place that assembles
  core + infrastructure.
* **factory** — a `boot/` function that builds a wired object graph.

## Common mistakes / conflations

* Putting business or command logic into boot/factories.
* Making core or infrastructure import `boot/` to obtain configuration or
  wiring (layering violation).
* Baking the "one session == one scenario" shortcut into factories when the
  root contract requires `SNXSession 1 -> N SNXShell`.
* Deciding the acting Linux user inside scenarios/security rather than
  composing it here from scenario identities.

## Current-state note

`core/runtime/runtime.py` (via `SNXRuntime.create_session`) currently serves as
the effective composition point: it selects the initial non-root user, builds
VFS + registry + shell, and attaches one shell per scenario identifier to an
app-level `SNXSession` keyed by `session_id`. Reusing `session_id` with another
scenario keeps both shells alive. The API still routes on `session_id` alone;
`boot/` should not introduce shortcuts that bypass the documented ownership
matrix or deepen that one-shell-per-session external view.