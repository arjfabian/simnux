# Scenario Contract (`core/scenarios/`)

Refines the root SIMNUX Architecture Contract for this directory and its
descendants. Must not contradict the root document.

## Role

`SNXScenario` represents one simulated Linux world. It is the scenario
definition and container for all scenario-scoped entities, loaded from YAML and
treated as immutable at runtime.

## Owns

* scenario definition (name, hostname, starting directory, configuration,
  objectives, triggers);
* the simulated Linux identities that exist inside the scenario
  (`SNXScenario.users`, `SNXScenario.groups`);
* the filesystem base state (nodes owned by the scenario's identities);
* any other YAML-defined scenario properties.

## Must NOT own

`SNXScenario` must NOT contain any mutable interaction state belonging to a
particular session/shell:

* current Linux user (the active identity is selected by `SNXShell`);
* current working directory of a shell;
* shell history / environment of a specific interaction;
* pending input / suspended command state;
* scenario progress for a specific client;
* session token / client identity.

## Relationships

```
SNXScenario 1 ─── 1 SNXShell ─── N ─── 1 SNXSession
```

* One scenario is referenced by exactly one `SNXShell` at a time (and that
  shell may in turn belong to an `SNXSession`).
* The same scenario definition may conceptually back different shells/sessions.
* `SNXUser`/`SNXGroup` instances are owned by the scenario and referenced by
  filesystem nodes (`SNXNode.owner`, `SNXNode.group`) and by a shell as its
  current user.

## Invariants

* A scenario definition is immutable after load; there is no scenario-local
  "current user" or "current directory" field.
* Two shells referencing the same (or equivalent) scenario never share
  interaction state — that state lives in each `SNXShell`.
* A Linux identity is only valid within the scenario that owns it.

## Dependency direction

* `core/scenarios/` may depend on `core/filesystem/` (node types for base
  state) and `security/` (identity primitives).
* It must NOT depend on `core/shell/`, `core/sessions/`, `core/commands/`,
  `infrastructure/`, or `boot/`.
* The loader must stay decoupled from HTTP/API and from session lifecycle.

## Terminology

* **scenario-scoped identity** — `SNXUser`/`SNXGroup` that exists only inside
  this scenario.
* **world state** — everything the scenario owns (definition, filesystem,
  identities). The counterpart of shell **interaction state**.
* **starting directory** — initial cwd defined by the scenario; shells may
  diverge from it.

## Common mistakes / conflations

* Giving the scenario a current user/cwd to solve "which user is logged in".
  Selection of the active identity belongs to `SNXShell`.
* Reintroducing a `username` on the scenario; the scenario owns a set of
  identities, not a single active one.
* Reusing one scenario instance as mutable per-client storage (progress,
  objectives state for a specific user).
* Overloading scenarios or their identities with client/session identity.

## Current-state note

The active `SNXUser` is selected in `SNXRuntime.create_session`
(`core/runtime/runtime.py`) — the first non-`root` user by `identifier` — and
passed into `SNXShell`. `scenario.username` has been removed. The selected user
is carried by the shell's interaction state (per this contract), not the
app-level `SNXSession`.