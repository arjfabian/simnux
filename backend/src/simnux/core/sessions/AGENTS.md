# Session Contract (`core/sessions/`)

Refines the root SIMNUX Architecture Contract for this directory and its
descendants. Must not contradict the root document.

## Role

`SNXSession` is the SIMNUX **application-level** session: the stateful
connection between the frontend/client and the backend, and the switch/router
for the user's active scenario shells.

## Owns

* the `SNXSession` identifier/token;
* the set (index) of `SNXShell` instances currently open under that session;
* shell dispatch: selecting the correct `SNXShell` for an incoming request.

## Must NOT own

`SNXSession` must NOT own any simulated-world or scenario-bound interaction
state:

* Linux `SNXUser`/`SNXGroup` (current or otherwise);
* current working directory;
* shell history;
* environment variables;
* filesystem state;
* scenario objectives/progress;
* pending input / suspended command state;
* scenario-specific configuration or command state.

All of the above belong to `SNXShell`. `SNXSession` is never a simulated Linux
identity and never identifies a scenario.

## Relationships

```
SNXSession 1 ─── N SNXShell ─── 1 SNXScenario
```

* A session may hold several shells, one per scenario the user has opened
  (e.g. `SNXSession.shells.add(SNXShell("hello"))` alongside
  `SNXSession.shells.add(SNXShell("mission-1"))`).
* The command flow crosses: frontend -> `SNXSession` -> appropriate `SNXShell`
  -> `SNXScenario` state -> `SNXShell` -> `SNXSession` -> frontend.
* `SNXSession` depends on `SNXShell` (and through it, on `SNXScenario`).

## Invariants

* A session token identifies the SIMNUX session — never a Linux user, never a
  scenario.
* One session -> zero or more shells; each shell belongs to exactly one
  session and exactly one scenario.
* `SNXSession` must never expose `user`, `cwd`, `history`, or other
  interaction state as its own fields/properties.

## Dependency direction

* `core/sessions/` may depend on `core/shell/`, `core/scenarios/`,
  `core/filesystem/`, and `security/` types.
* It must NOT depend on `core/commands/`, `infrastructure/`, `boot/`, or any
  HTTP/runtime wiring detail.

## Terminology

* **session token** — identifies `SNXSession`; not a Linux user, not a
  scenario.
* **shell dispatch** — this module's job of routing a request to the right
  `SNXShell`.
* **scenario selection** — (future, not implemented) the frontend
  communicating which shell a request belongs to. See root document.

## Common mistakes / conflations

* Storing `current_directory`, `history`, or `user` on `SNXSession`. These are
  `SNXShell` interaction state.
* Exposing the session as a Linux identity (`session.username` and similar).
  Simulated Linux identity flows from `SNXScenario` identities.
* Adding a new "scenario run" abstraction because state currently sits in the
  `SNXSession` dataclass. Do not rename `SNXSession`; recable it around the
  ownership matrix.
* Treating one open scenario as "the" session, or assuming one session equals
  one shell.

## Current-state note

Today the `SNXSession` dataclass still stores scenario-bound interaction state
(`scenario`, `user`, `current_directory`, `history`, `environment`, pending
state), and `SNXRuntime` (`core/runtime/runtime.py`) keys live shells by a
per-scenario identifier. This is recognized mid-migration drift. The target is
this contract: `SNXSession 1 -> N SNXShell`, with interaction state on
`SNXShell`. Keep behaviour working while recabling; do not rename classes or
add `SNXScenarioRun`.