# Filesystem Contract (`core/filesystem/`)

Refines the root SIMNUX Architecture Contract for this directory and its
descendants. Must not contradict the root document.

## Role

`core/filesystem/` implements the simulated Linux filesystem: the node model
(`SNXNode`) and the VFS layer (`SNXFileSystem`) with ownership semantics,
path resolution, and per-command filesystem views/mutations.

## Owns

* the simulated filesystem node tree built over a scenario's base state;
* node ownership and permission representation;
* VFS operations and their semantics (path resolution, redirects, deltas,
  tombstones, absolute/relative paths, home directory handling).

## Must NOT own

* Client/session state — filesystems do not manage `SNXSession`,
  `SNXShell`, or authentication;
* the current acting Linux user (the shell decides who acts; the filesystem
  only evaluates ownership/permissions against identities it references);
* scenario definitions, objectives, triggers, or progress;
* command execution or dispatch.

## Relationships

* A filesystem is created from an `SNXScenario`'s filesystem base state and is
  used by the `SNXShell`. Different shells/scenarios have independent
  filesystems.
* `SNXNode.owner` references a scenario-scoped `SNXUser`;
  `SNXNode.group` references a scenario-scoped `SNXGroup`.

## Invariants

* `SNXNode.owner` is always an `SNXUser`; `SNXNode.group` is always an
  `SNXGroup` — never a bare string such as `"root"`.
* Ownership is scenario-local; a node never references a global SIMNUX client
  identity.
* System-created nodes and tombstones needing root ownership use valid
  scenario-local root `SNXUser`/`SNXGroup` objects.
* VFS semantics, permission representation, command semantics, and path
  resolution are preserved. Do not redesign the VFS.

## Dependency direction

* `core/filesystem/` may depend on `security/` identity primitives.
* It must NOT depend on `core/sessions/`, `core/shell/`, `core/scenarios/`
  (scenario definition loading) or on `infrastructure/`/`boot/`.
* Consumers (shell, commands) depend on it.

## Terminology

* **owner** — the scenario-local `SNXUser` owning a node.
* **group** — the scenario-local `SNXGroup` associated with a node.
* **base state** — the immutable filesystem contributed by the scenario.
* **acting identity** — the scenario-local user performing a command (shell
  interaction state), distinct from any node's stored owner/group.

## Common mistakes / conflations

* Using strings for `SNXNode.owner`/`group` — must be real `SNXUser`/`SNXGroup`.
* Referencing a client identity or session token in ownership.
* Making the filesystem aware of "the logged-in user" as its own state;
  the acting identity comes from the shell/scenario, not the filesystem.

## Current-state note

Ownership has already migrated from strings to `SNXUser`/`SNXGroup` objects
and VFS root constants (`_ROOT_USER`/`_ROOT_GROUP`) exist for system-created
nodes. Retain this; do not regress to string ownership.