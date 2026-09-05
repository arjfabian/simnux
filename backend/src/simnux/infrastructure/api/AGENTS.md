# API Contract (`infrastructure/api/`)

Refines the SIMNUX Architecture Contract. Stronger than the
`infrastructure/` contract; must not contradict the root document.

## Role

The API is an HTTP adapter between external clients and the SIMNUX core. Its
responsibility is routing and translation, not simulation.

## Owning

* endpoint definitions, request validation, and response serialization;
* mapping between external requests and core calls (session/shell dispatch).

## Must NOT own

* scenario, filesystem, command, or permission semantics — the API must not
  re-implement any core logic;
* the session/shell/scenario lifecycle beyond calling into it;
* authentication as a simulated Linux identity.

## Request flow

```
Frontend -> API -> SNXSession -> SNXShell -> SNXScenario -> result
  -> SNXShell -> SNXSession -> API -> Frontend
```

The API must not bypass the `SNXSession`/`SNXShell` boundaries by reaching
into scenario internals from route handlers.

## Invariants

* API requests identify the SIMNUX session and, in the future, the target
  scenario/shell.
* A session token is never treated as a Linux username and never as a scenario
  identifier.
* Keep existing endpoints, command behavior, response contracts, and route
  semantics unchanged unless explicitly requested.

## Frontend scenario selection (future; do not implement)

If a user opens `<frontend>/hello` and later `<frontend>/mission-1`, the
backend must eventually distinguish which `SNXShell` a request belongs to, so
two browser tabs cannot send commands to different shells under one
`SNXSession`. Documented only; do NOT implement and do NOT change API routing
now.

## Dependency direction

`infrastructure/api/` depends on `core/` abstractions and `infrastructure/`
support types. Core never depends on this directory.

## Terminology

* **route handler** — an adapter, not a logic container.
* **session token** — identifies the SIMNUX session (root terminology).

## Common mistakes / conflations

* Implementing command/VFS logic in handlers.
* Assuming one shell per session when interpreting `session_id`.
* Treating `session_id` as a Linux identity.

## Current-state note

Today the runtime keys one shell per scenario run by `session_id`, so the API
behaves like one scenario per session. That is cited mid-migration drift in
the root and `infrastructure/` contracts; do not lock it into the API
contract permanently.