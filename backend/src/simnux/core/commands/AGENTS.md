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

* The shell builds a `CommandContext` (shell reference, filesystem,
  execution context, dispatcher) and calls the dispatcher.
* Commands interact with the simulated world through that context:
  filesystem (passing `context.execution_context` as the authorization
  subject) and the scenario state reachable via the shell.
* The dispatch flow stays within the responsibility boundary
  `SNXSession -> SNXShell -> command pipeline -> SNXScenario` described in the
  root document. Do not redesign the command system.

## Invariants

* A command never treats the session object as an identity: the current
  subject is the scenario-scoped `ExecutionContext` from
  `CommandContext.execution_context`, not `session.username` or any
  session-bound identity field.
* Consent/prompt style or identity-dependent commands (`whoami`, prompt
  rendering, home-directory expansion) read the subject's effective identity
  from `ctx.execution_context.credentials.effective_user`.
* All filesystem operations in commands pass `execution=ctx.execution_context`
  (never a bare `SNXUser` and never `ctx.shell.user`).
* Commands resolve simulated users/groups against the owning `SNXScenario`, not
  against a global registry.

## Dependency direction

* `core/commands/` may depend on `core/filesystem/`, `core/scenarios/`,
  `core/scenarios` state primitives, and `security/` types.
* It must NOT depend on `infrastructure/`, `boot/`, or on `core/sessions/`
  internals for state; the context it receives is prepared by the shell.

## Terminology

* **CommandContext** — the bounded set of references (shell, filesystem,
  execution context, dispatcher) a command needs; not a grab-bag for global
  state.
* **execution context** — the scenario-scoped subject (`security/execution`)
  the command runs as and passes to the VFS.
* **action/result** — structured `CommandResult` output with exit code.

## Common mistakes / conflations

* Reading the current user off the session object or the scenario definition
  (either is the `username` conflation that was removed); use
  `ctx.execution_context`.
* Reaching from a command into scenario internals that the shell should
  mediate.
* Storing per-interaction state on the scenario or session to make a command
  work.
* Passing `ctx.shell.user` to filesystem/stream operations after the migration
  to `ExecutionContext`.

## Current-state note

Commands receive a `CommandContext` whose `execution_context` is the source of
the subject for authorization: filesystem calls and `FileStreamWriter` pass
`execution=ctx.execution_context`, and display commands read
`ctx.execution_context.credentials.effective_user`. This matches the target
contract; keep it. Do not reach for session-bound state or redesign the
pipeline.