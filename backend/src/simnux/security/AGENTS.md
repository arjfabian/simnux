# Security Identity Contract (`security/`)

Refines the root SIMNUX Architecture Contract for this directory and its
descendants. Must not contradict the root document.

## Role

`security/` defines the scenario-local Linux identity primitives used
throughout SIMNUX:

* `SNXUser` (`user_id` + `identifier`);
* `SNXGroup` (`group_id` + `identifier`).

These are value types describing identities **inside a simulated scenario**.
They are not SIMNUX application users, not authentication principals, and not
session identities.

## Owns

* The `SNXUser` / `SNXGroup` data model and any scenario-local permissions
  built on them.

## Must NOT own

* Client/frontend identities;
* authentication, credentials, tokens, or authorization of SIMNUX users;
* session tokens (`SNXSession` identification);
* any reference to sessions, shells, scenarios, or the runtime;
* simulated filesystem content or VFS behaviour.

## Relationships

Scenario-local identities may be referenced by:

* `SNXScenario.users` / `SNXScenario.groups` (the identities that exist);
* `SNXShell` as the current acting Linux user;
* filesystem ownership: `SNXNode.owner` (an `SNXUser`) and
  `SNXNode.group` (an `SNXGroup`).

Consumers depend on `security/`; `security/` depends on nothing.

## Invariants

* An identity is valid only within the scenario that owns it; there is no
  global cross-scenario `SNXUser`/`SNXGroup` registry.
* A Linux identity and a SIMNUX client identity are different concepts even
  when they represent the same human.
* `user_id`/`group_id` are the numeric Linux ids; `identifier` is the Linux
  name (e.g. `"root"`). Do not use one where the other is meant.

## Dependency direction

`security/` is a leaf. It MUST NOT import any SIMNUX module (not even
`core/`). Everything else may import it.

## Terminology

* **scenario-local identity** — an `SNXUser`/`SNXGroup` owned by an
  `SNXScenario`.
* **identifier** — the simulated Linux name; **not** a username for the SIMNUX
  application.
* **owner/group** — filesystem node references to scenario-local identities,
  never bare strings and never client identities.

## Common mistakes / conflations

* Overloading `SNXUser` as a SIMNUX client account or session identity.
* Using bare strings such as `"root"` for node ownership (must be `SNXUser`
  /`SNXGroup` objects from the owning scenario).
* Naming this package "security" and then importing authentication or
  infrastructure concepts into it. Its scope is scenario-local Linux identity
  primitives; keep it a dependency-free leaf.
* Reading the "current user" from a session rather than from shell interaction
  state that references scenario identities.

## Current-state note

The current `SNXUser`/`SNXGroup` model already matches this contract (frozen
dataclasses with `user_id`/`identifier` and `group_id`/`identifier`).
Filesystem nodes migrated from string ownership to real `SNXUser`/`SNXGroup`
objects; retain that direction.