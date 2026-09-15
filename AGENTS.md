# SIMNUX Architecture Contract

This document is the canonical SIMNUX architecture contract. More specific
`AGENTS.md` files under `backend/src/simnux/` refine these contracts for their
directory and descendants; they must strengthen, never contradict, this root
document.

## Canonical model

SIMNUX has three distinct runtime concepts in one strict hierarchy:

```
SNXSession
    └── SNXShell
          └── SNXScenario
```

* `SNXSession` — the application-level connection between the frontend/client
  and the backend. It is the stateful client/backend session and the
  switch/router for the user's active scenario shells. One session owns zero or
  more `SNXShell` instances.
* `SNXShell` — one interactive shell attached to exactly one `SNXScenario`. It
  owns the mutable interaction state required to talk to that scenario
  (current execution context, cwd, history, environment, pending input,
  progress).
* `SNXScenario` — one simulated Linux world: the scenario definition and its
  scenario-scoped entities (hostname, users, groups, filesystem, objectives,
  triggers, configuration).

The relationship cardinality is:

```
SNXSession 1 ─── N SNXShell ─── 1 SNXScenario
```

A command conceptually flows: frontend -> `SNXSession` -> (appropriate)
`SNXShell` -> `SNXScenario` / scenario state -> `SNXShell` -> `SNXSession` ->
frontend. This describes the responsibility boundary, not a literal call chain.

## Canonical terminology

Future changes MUST use these terms with these meanings:

| Term | Meaning |
| --- | --- |
| SIMNUX session (`SNXSession`) | App-level client/backend session; shell router. Never a Linux identity. |
| shell (`SNXShell`) | Per-scenario interaction context owned by a session. |
| scenario (`SNXScenario`) | Immutable simulated Linux world; scenario-scoped entity container. |
| simulated Linux identity (`SNXUser`, `SNXGroup`) | Scenario-scoped identity inside a simulated world. NOT a SIMNUX client account. |
| execution credentials | The scenario-scoped identity and group set under which a specific piece of work is performed (who an operation runs as): real/effective identity, primary + supplementary groups, reserved privilege information. Owned by `security/`, held by `SNXShell` via the current execution context. |
| execution context | The security state under which work is performed: current execution credentials (extensible toward a future execution view / filesystem-root restriction). Owned by `SNXShell`; commands and the VFS receive it as the authorization subject. |
| authorization | The security-layer decision of whether an execution context may perform an abstract requested action (`AccessRight`) on a protected resource (owner/group/permission profile). Owned by `security/`; never by sessions, shells, commands, or the filesystem. |
| interaction state | Where "this particular interaction currently is": current execution context, cwd, history, env, pending input, progress. Owned by `SNXShell`. |
| world state | What "the simulated world contains": scenario definition, filesystem, identities. Owned by `SNXScenario`. |
| session token | Identifies the SIMNUX session. Never identifies a Linux user and never identifies a scenario. |
| shell dispatch | The act of `SNXSession` selecting the correct `SNXShell` for a request. |
| scenario selection | (Future) frontend carrying which scenario/shell a request belongs to, so two tabs cannot collide. Documented, NOT implemented. |

## State ownership matrix

| Component | Owns | Must NOT own |
| --- | --- | --- |
| `SNXSession` | session token/identifier; the set of `SNXShell` instances; shell dispatch. | Linux users/groups, execution credentials/context, cwd, history, environment, filesystem state, scenario objectives/progress, scenario-specific state. |
| `SNXShell` | all mutable interaction state for its scenario (see interaction state above), including the current execution context. | scenario definitions, scenario world state, client authentication/session identity, authorization policy. |
| `SNXScenario` | scenario definition and scenario-scoped entities (see world state above). | any interaction state belonging to a particular session/shell. |
| `SNXUser`/`SNXGroup` | a scenario-local Linux identity (`user_id`/`group_id` + `identifier`). | client identity, authentication, session state. |
| `security/` (identity, execution, authorization) | scenario-local identity primitives; execution credentials and execution context; the authorization policy over abstract protected resources. | filesystem implementation (nodes, paths, ownership storage), commands, session/shell state, client identity. |

## Dependency direction

* `boot/` composes everything and depends on `infrastructure/` and `core/`.
* `infrastructure/` depends on `core/` abstractions. Core MUST NOT depend on
  `infrastructure/` or `boot/`.
* Within `core/`: `sessions/` dispatches to `shell/`; `shell/` operates on
  `scenarios/`; `scenarios/` defines filesystem base state and identities;
  `filesystem/` and `scenarios/` reference `security/` identity primitives;
  `commands/` receives context built by the shell.
* Within `security/`: execution (credentials + context) depends on identity
  primitives; authorization depends on execution. Execution context/credentials
  `↓` authorization `↓` VFS: the filesystem constructs abstract authorization
  requests over its node state and asks authorization whether an execution
  context may perform the requested action. The filesystem never defines
  execution identity or privilege semantics.
* `security/` is a leaf: it MUST NOT import any SIMNUX module.

Do not move concepts between these boundaries merely to simplify imports.

## Boundaries

* `backend/src/simnux/security/` — scenario-local identity primitives; execution credentials/context; authorization policy.
* `backend/src/simnux/core/scenarios/` — immutable scenario definitions loaded from YAML.
* `backend/src/simnux/core/shell/` — scenario interaction state and behavior.
* `backend/src/simnux/core/sessions/` — the global SIMNUX client/backend session.
* `backend/src/simnux/core/commands/` — the command parser/dispatcher/registry and command implementations.
* `backend/src/simnux/core/filesystem/` — the simulated filesystem and ownership semantics.
* `backend/src/simnux/infrastructure/` — adapters of core to external interfaces (API, observability).
* `backend/src/simnux/boot/` — composition root; wires configuration, core, infrastructure, lifecycle.

## Frontend scenario selection (future; do not implement)

A future concern that must be documented but NOT implemented now: if a user
opens `<frontend>/hello` and later `<frontend>/mission-1`, the backend must be
able to distinguish which `SNXShell` a request belongs to. The frontend will
eventually need to retain/communicate the scenario identity (or an equivalent
shell identifier) so that two browser tabs cannot accidentally send commands to
different shells under the same `SNXSession`. Until then, do not change API
behavior or session routing.

## Known current-state drift

The session/shell/scenario rewiring has landed. `SNXSession`
(`core/sessions/runtime.py`) is a shell router (`session_id` + `shells` dict)
owning no interaction state; `SNXShell` owns all interaction state (execution
context, cwd, env, history, pending input/progress);
`CommandContext.shell`/`CommandContext.execution_context` are the source of
interaction state for commands and prompt rendering. Recognition of drift that
remains:

* `SNXRuntime` (`core/runtime/runtime.py`) keys its app-level session index by
  `session_id` and attaches one shell per scenario identifier to it. Reusing
  `session_id` with a different scenario keeps both shells under the same
  session. The target `SNXSession 1 -> N SNXShell` structure is in place
  internally.
* The API and public routing still address a single `session_id` (scenario
  selection is documented but NOT implemented), so externally one shell per
  session is reached today. Do not change API behavior or session routing yet.

## Migration rules

* Do NOT rename `SNXSession`, `SNXShell`, or `SNXScenario`.
* Do NOT introduce an `SNXScenarioRun` abstraction merely because state
  currently sits inside `SNXSession`.
* Do NOT redesign the command system or the VFS.
* Do NOT implement multi-scenario sessions or API changes yet.
* Recable existing objects around the documented ownership matrix.

## Preservation rule

Refactors must preserve the existing command system, VFS semantics, scenario
behavior, and public API behavior unless the task explicitly changes them.
Prefer recabling existing objects over introducing replacement abstractions.

## AGENTS hierarchy

More specific `AGENTS.md` files define stronger contracts for their directory
and descendants. See `backend/src/simnux/core/sessions/AGENTS.md`,
`backend/src/simnux/core/shell/AGENTS.md`,
`backend/src/simnux/core/scenarios/AGENTS.md`,
`backend/src/simnux/security/AGENTS.md`,
`backend/src/simnux/core/filesystem/AGENTS.md`,
`backend/src/simnux/core/commands/AGENTS.md`,
`backend/src/simnux/infrastructure/AGENTS.md`,
`backend/src/simnux/boot/AGENTS.md`.