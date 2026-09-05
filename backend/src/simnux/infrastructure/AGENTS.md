# Infrastructure Contract (`infrastructure/`)

Refines the root SIMNUX Architecture Contract for this directory and its
descendants. Must not contradict the root document.

## Role

`infrastructure/` adapts the SIMNUX core to external interfaces. It is the
layer where HTTP/API concerns (`api/`) and observability/snapshots
(`observability/`) live. It carries no simulated-world or session semantics of
its own; it translates external requests into core calls and core results into
external responses.

## Owns

* HTTP routing, request/response adapters, and serialization (`api/`);
* observability: runtime/shell snapshots and any telemetry bridges
  (`observability/`);
* the plumbing that turns an incoming request into an `SNXSession`/`SNXShell`
  dispatch on the core side.

## Must NOT own

* scenario definitions, filesystem behavior, or command semantics — the API
  must not re-implement core logic;
* the `SNXSession`/`SNXShell`/`SNXScenario` relationship itself; it only
  invokes it;
* authentication/identity logic that belongs to the core boundaries
  (scenario-local identities stay scenario-scoped; app-level sessions are the
  only client identity boundary);
* VFS/command/parser internals.

## Relationships

* Infrastructure depends on core abstractions (sessions, shells, scenarios,
  commands results) via `core/runtime/`-style entry points.
* Core modules MUST NOT depend on `infrastructure/`. Existing imports of
  `infrastructure/observability/snapshots` in `core/shell/runtime.py` are
  known drift; do not widen them.
* `boot/` composes infrastructure and core together.

## Invariants

* The command flow is preserved end-to-end:
  frontend -> API -> `SNXSession` -> `SNXShell` -> `SNXScenario` -> result ->
  `SNXShell` -> `SNXSession` -> API -> frontend.
* A session token routed through the API identifies the SIMNUX session; it is
  never interpreted as a Linux username and never as a scenario.
* API behavior, endpoints, and response contracts stay unchanged unless
  explicitly requested (see root "Frontend scenario selection").

## Dependency direction

`infrastructure/` depends on `core/`. Nothing in `core/` depends on
`infrastructure/` or `boot/`.

## Terminology

* **adapter** — any `infrastructure/` component translating external/external
  concerns.
* **route handler** — an HTTP adapter that calls core; it does not implement
  scenario or filesystem semantics.
* **session token** — opaque identifier of the SIMNUX session (see root).

## Common mistakes / conflations

* Implementing command or VFS logic in route handlers.
* Reaching directly into scenario internals, bypassing the
  `SNXSession`/`SNXShell` boundary.
* Treating a session token as a Linux username or as a scenario identifier.
* Assuming one shell per session in the API plumbing (a session will
  eventually hold many shells; scenario selection is documented but NOT
  implemented).

## Current-state note

The rewiring has landed: `SNXRuntime` maintains an app-level `SNXSession`
(`session_id`) that holds one `SNXShell` per scenario identifier. The API today
still addresses that `session_id` directly, so GET `/api/sessions/{id}` and
DELETE `/sessions/{id}` reach a single shell for now. This is acceptable while
scenario selection remains unimplemented; do not change routing or response
behavior until explicitly tasked.