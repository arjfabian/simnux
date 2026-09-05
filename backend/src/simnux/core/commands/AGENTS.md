# Command Contract (`core/commands/`)

Refines the root SIMNUX Architecture Contract for this directory and its
descendants. Must not contradict the root document.

## Role

`core/commands/` is the command pipeline: parsing, validation, dispatch, and
the implementations of the simulated Linux commands. It receives execution
context from the shell and produces `CommandResult`s.

## Owns

* the command parser;
* the dispatcher and pipeline (including logical operators `&&`/`||`);
* the command registry and loader;
* the command implementations under `standard/` and friends;
* the `CommandContext` plumbing handed to commands.

## Must NOT own

* scenario definitions or simulated-world entity containers;
* the `SNXSession`/`SNXShell` relationship or shell dispatch;
* client/session authentication or identity;
* HTTP/API adaptation — commands are invoked through the shell, not by routes.

## Relationships

* The shell builds a `CommandContext` (session reference, filesystem,
  dispatcher) and calls the dispatcher.
* Commands interact with the simulated world through that context:
  filesystem, and the scenario state reachable via the shell/session.
* The dispatch flow stays within the responsibility boundary
  `SNXSession -> SNXShell -> command pipeline -> SNXScenario` described in the
  root document. Do not redesign the command system.

## Invariants

* A command never treats the session object as an identity: the current Linux
  user is a scenario-scoped `SNXUser` from shell interaction state, not
  `session.username` or any session-bound identity field.
* Consent/prompt style or identity-dependent commands (`whoami`, prompt
  rendering, home-directory expansion) read the acting user from the shell's
  interaction state / scenario identities.
* Commands resolve simulated users/groups against the owning `SNXScenario`, not
  against a global registry.

## Dependency direction

* `core/commands/` may depend on `core/filesystem/`, `core/scenarios/`,
  `core/scenarios` state primitives, and `security/` types.
* It must NOT depend on `infrastructure/`, `boot/`, or on `core/sessions/`
  internals for state; the context it receives is prepared by the shell.

## Terminology

* **CommandContext** — the bounded set of references (session/shell, filesystem,
  dispatcher) a command needs; not a grab-bag for global state.
* **acting identity** — the scenario-local user the command runs as.
* **action/result** — structured `CommandResult` output with exit code.

## Common mistakes / conflations

* Reading the current Linux user off the session object or the scenario
  definition (either is the `username` conflation that was removed).
* Reaching from a command into scenario internals that the shell should
  mediate.
* Storing per-interaction state on the scenario or session to make a command
  work.

## Current-state note

Commands currently receive a `CommandContext` whose `session` reference still
carries the acting user and cwd (mid-migration). `whoami` and prompt rendering
read `session.user.identifier`. Keep behaviour working today; the future source
of truth is `SNXShell` interaction state. Do not redesign the pipeline.