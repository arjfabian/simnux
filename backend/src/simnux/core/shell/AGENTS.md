# Shell Contract (`core/shell/`)

Refines the root SIMNUX Architecture Contract for this directory and its
descendants. Must not contradict the root document.

## Role

`SNXShell` is the per-scenario interaction context and the
interface/middleware between `SNXSession` and `SNXScenario`. It is one
interactive shell attached to exactly one scenario.

## Owns

`SNXShell` owns all mutable **interaction state** for its scenario:

* current execution context (the scenario-scoped credentials under which this
  interaction's work runs — an `ExecutionContext` from `security/execution`);
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
* The authorization decision — the shell carries an `ExecutionContext` and
  passes it to commands/VFS, but never decides who may act.

## Relationships

```
SNXShell 1 ─── 1 SNXScenario
```

* A shell belongs to exactly one `SNXSession` and operates on exactly one
  `SNXScenario`.
* Multiple shells may exist under one `SNXSession`, each against a different
  scenario; they keep independent interaction state (e.g. shell "hello" at
  `/etc` while shell "mission-1" is at `/home/user`).
* The current execution context must be built from `SNXUser`/`SNXGroup`
  drawn from the shell's scenario — never a client identity. The shell may
  expose the effective identity as a display convenience (`user` property),
  but commands and the VFS authorize via `execution_context`.

## Invariants

* Everything describing "where this particular interaction currently is"
  (cwd, execution context, history, env, pending input, progress) belongs to
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

* **interaction state** — owned here: cwd, execution context, history, env,
  pending input, progress.
* **world state** — owned by `SNXScenario`: definition, filesystem,
  identities.
* **execution context** — the scenario-scoped `ExecutionContext` this shell
  acts as (whose work is performed); the authorization subject passed to
  commands and the VFS.

## Common mistakes / conflations

* Storing a scenario definition inside shell state; the shell references
  `SNXScenario`, it does not re-host the world.
* Making `SNXShell` act as the global client session (one session can hold
  many shells).
* Representing the acting context with anything other than a scenario-derived
  `ExecutionContext` from `security/execution`.
* Building credentials ad hoc inside the shell; the shell is given its initial
  `ExecutionContext` by the composition root.
* Commands or the prompt reading the current user through the session object
  (`session.user`); the source of truth is shell interaction state (
  `shell.execution_context`).

## Current-state note

The rewiring has landed. `SNXShell` (`core/shell/runtime.py`) now owns all
interaction state directly (`execution_context`, `current_directory`,
`environment`, `history`, `pending_input`/`pending_state`, task progress) and
no longer reads it through a session reference. `CommandContext.shell` /
`CommandContext.execution_context` are the source of interaction state for
commands and prompt rendering. `SNXRuntime` attaches one shell per scenario
identifier to an app-level `SNXSession`; reusing `session_id` with a different
scenario keeps both shells alive under the same session. The remaining gap is
that the API still routes by `session_id` alone (scenario selection is
documented but not yet implemented), so externally only one shell per session
is reached today. Keep that; do not rename classes or add `SNXScenarioRun`.