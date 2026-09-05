# Shell Contract (`core/shell/`)

Refines the root SIMNUX Architecture Contract for this directory and its
descendants. Must not contradict the root document.

## Role

`SNXShell` is the per-scenario interaction context and the
interface/middleware between `SNXSession` and `SNXScenario`. It is one
interactive shell attached to exactly one scenario.

## Owns

`SNXShell` owns all mutable **interaction state** for its scenario:

* current Linux user (a scenario-scoped `SNXUser`);
* current working directory;
* environment variables;
* command history;
* pending input / suspended command state;
* scenario progress for this interaction;
* shell-level execution state (parser, dispatcher, registry, lock).

## Must NOT own

* Scenario definitions or scenario world state — it holds a reference to one
  `SNXScenario`, never a copy/cache of the world.
* SIMNUX client authentication/session identity. `SNXShell` is a scenario
  interaction context, not a client account.
* The global session's shell set / dispatch responsibility (that is
  `SNXSession`).

## Relationships

```
SNXShell 1 ─── 1 SNXScenario
```

* A shell belongs to exactly one `SNXSession` and operates on exactly one
  `SNXScenario`.
* Multiple shells may exist under one `SNXSession`, each against a different
  scenario; they keep independent interaction state (e.g. shell "hello" at
  `/etc` while shell "mission-1" is at `/home/user`).
* The current Linux user must be a `SNXUser` drawn from the shell's scenario —
  never a client identity.

## Invariants

* Everything describing "where this particular interaction currently is"
  (cwd, current user, history, env, pending input, progress) belongs to
  `SNXShell`.
* Everything describing "what the simulated world contains" belongs to
  `SNXScenario`.
* Two shells on the same scenario never share interaction state.

## Dependency direction

* `core/shell/` may depend on `core/scenarios/`, `core/filesystem/`,
  `core/commands/`, and `security/` types.
* It must NOT depend on `core/sessions/` for state storage (sessions consume
  shells), on `infrastructure/`, or on `boot/`. Existing imports of
  `infrastructure/observability/snapshots.py` and `boot/config.py` are known
  drift; do not widen them.

## Terminology

* **interaction state** — owned here: cwd, current user, history, env,
  pending input, progress.
* **world state** — owned by `SNXScenario`: definition, filesystem,
  identities.
* **current Linux user** — the scenario-scoped `SNXUser` this shell acts as.

## Common mistakes / conflations

* Storing a scenario definition inside shell state; the shell references
  `SNXScenario`, it does not re-host the world.
* Making `SNXShell` act as the global client session (one session can hold
  many shells).
* Representing the acting Linux user with anything other than a scenario
  `SNXUser`.
* Commands or the prompt reading the current user through the session object
  (`session.user`); the source of truth is shell interaction state.

## Current-state note

Today the shell's interaction state still lives on the `SNXSession` dataclass
(`scenario`, `user`, `current_directory`, `history`, `environment`, pending
fields) and `SNXShell` (`core/shell/runtime.py`) reads/writes it through that
reference. `SNXRuntime` currently creates one shell per scenario run keyed by a
per-scenario identifier. The target is this contract: move interaction state
onto `SNXShell` and have `SNXSession` dispatch to shells — without renaming
classes, adding `SNXScenarioRun`, or changing command/VFS behaviour.