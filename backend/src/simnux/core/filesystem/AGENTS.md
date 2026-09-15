# Filesystem Contract (`core/filesystem/`)

Refines the root SIMNUX Architecture Contract for this directory and its
descendants. Must not contradict the root document.

## Role

`core/filesystem/` implements the simulated Linux filesystem: the node model
(`SNXNode`), the permission encoding (mode bits, presets, symbolic renderers),
and the VFS layer (`SNXFileSystem`) with ownership semantics, path resolution,
and per-command filesystem views/mutations. The VFS is the *question-asker* for
authorization: it constructs abstract requests over its node state and asks
`security/authorization` whether an execution context may act.

## Owns

* the simulated filesystem node tree built over a scenario's base state;
* node ownership and permission representation (encoding/decoding, presets);
* VFS operations and their semantics (path resolution, redirects, deltas,
  tombstones, absolute/relative paths, home directory handling);
* the construction of `ProtectedResource`/`AccessRequest` values from node
  state and the *call* to `AuthorizationPolicy` for every gated operation.

## Must NOT own

* Client/session state — filesystems do not manage `SNXSession`,
  `SNXShell`, or authentication;
* the authorization decision — the VFS must ask `AuthorizationPolicy`, never
  decide itself by reading bits or checking user ids;
* execution identity or privilege semantics — who can do what is a
  `security/` concern; the VFS carries an `ExecutionContext` but never
  defines one or mutates credentials;
* group membership — `SNXGroupMembership` exists only for credential
  construction at the composition root, never in the VFS;
* scenario definitions, objectives, triggers, or progress;
* command execution or dispatch.

## Relationships

* A filesystem is created from an `SNXScenario`'s filesystem base state and is
  used by the `SNXShell`. Different shells/scenarios have independent
  filesystems.
* `SNXNode.owner` references a scenario-scoped `SNXUser`;
  `SNXNode.group` references a scenario-scoped `SNXGroup`; node permission
  flags come from `security/authorization`.
* Every gated VFS method receives an `execution: ExecutionContext` (the
  authorization subject) — from the shell for commands, or
  `ExecutionContext.root()` for system-level operations.
* The VFS depends on `security/execution` (the context type) and
  `security/authorization` (the policy). `security/` never imports the
  filesystem.

## Invariants

* `SNXNode.owner` is always an `SNXUser`; `SNXNode.group` is always an
  `SNXGroup` — never a bare string such as `"root"`.
* Ownership is scenario-local; a node never references a global SIMNUX client
  identity.
* System-created nodes and tombstones needing root ownership use valid
  scenario-local root `SNXUser`/`SNXGroup` objects (`ExecutionContext.root()`
  supplies the identity for access decisions).
* The VFS never makes an authorization decision itself: it calls the
  `AuthorizationPolicy` it was constructed with (defaulting to a root
  policy). Denials are rendered by the policy, not hand-rolled in the VFS.
* VFS semantics, permission representation, command semantics, and path
  resolution are preserved. Do not redesign the VFS.

## Dependency direction

* `core/filesystem/` may depend on `security/` identity/execution/authorization
  abstractions.
* It must NOT depend on `core/sessions/`, `core/shell/`, `core/scenarios/`
  (scenario definition loading) or on `infrastructure/`/`boot/`.
* Consumers (shell, commands) depend on it.

## Terminology

* **owner** — the scenario-local `SNXUser` owning a node.
* **group** — the scenario-local `SNXGroup` associated with a node.
* **base state** — the immutable filesystem contributed by the scenario.
* **execution context** — the authorization subject for a VFS operation
  (current credentials), passed by the caller; never stored as filesystem
  state.

## Common mistakes / conflations

* Using strings for `SNXNode.owner`/`group` — must be real `SNXUser`/`SNXGroup`.
* Referencing a client identity or session token in ownership.
* Keeping "the logged-in user" as filesystem state; the acting credentials
  arrive per-call as an `ExecutionContext` from the shell.
* Re-implementing permission decisions in the VFS instead of delegating to
  `AuthorizationPolicy`.
* Passing a bare `SNXUser` to gated VFS operations; the subject is an
  `ExecutionContext`.

## Current-state note

`SNXFileSystem` already authorizes exclusively via `ExecutionContext` +
`AuthorizationPolicy`, nodes use `SNXUser`/`SNXGroup` ownership, and
`PermissionFlags`/`SNXPermissions`/`Access` now live in
`security/authorization/models.py` (reference, don't copy). The mode
encode/decode helpers and presets remain in `core/filesystem/models.py`.
VFS root constants `_ROOT_USER`/`_ROOT_GROUP` still exist for node ownership;
access decisions use `ExecutionContext.root()`. Retain these; do not regress
to bare-string ownership or per-call membership.