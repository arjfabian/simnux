# Security Contract (`security/`)

Refines the root SIMNUX Architecture Contract for this directory and its
descendants. Must not contradict the root document.

## Role

`security/` defines everything the simulated worlds need to *be* someone and
to authorize work — as abstraction, never implementation:

* `identity/` — scenario-local Linux identity primitives:
  `SNXUser` (`user_id` + `identifier`) and `SNXGroup`
  (`group_id` + `identifier`), plus scenario-local group membership.
* `execution/` — execution credentials (`ExecutionCredentials`) and the
  execution context (`ExecutionContext`) under which work is performed.
* `authorization/` — the authorization policy (`AuthorizationPolicy`), the
  abstract protected-resource request model (`ProtectedResource`,
  `AccessRequest`, `Access`, `PermissionFlags`, `SNXPermissions`) and the
  permission encoding used by `owner/group/other` profiles.

These are value types describing identities and security state **inside a
simulated scenario**. They are not SIMNUX application users, not
authentication principals, not session identities, and not client accounts.

## Subdomains and dependencies

* `identity` — leaf of the leaf. Defines `SNXUser`/`SNXGroup`/membership.
* `execution` — depends only on `identity`. `ExecutionCredentials`
  (real/effective identity, primary + supplementary groups, reserved
  privilege information) is built from an identity plus group membership;
  `ExecutionContext` wraps the current credentials.
* `authorization` — depends only on `execution`. `AuthorizationPolicy`
  decides whether an `ExecutionContext` may perform an abstract
  `AccessRight` on an abstract protected resource (owner/group/other
  permission profile). Group membership for authorization is taken from
  the execution context's credentials — never from a separate registry the
  writer (VFS/shell/command) injects.

## Owns

* The `SNXUser`/`SNXGroup` data model and scenario-local membership;
* execution credentials and the execution context;

* the authorization decision over abstract protected resources;
* the shared permission encoding/constants used by authorization.

## Must NOT own

* Client/frontend identities;
* authentication, account credentials, tokens, or SIMNUX user authorization;
* session tokens (`SNXSession` identification);
* any reference to sessions, shells, scenarios, or the runtime;
* simulated filesystem nodes, paths, content, or VFS behaviour (the VFS
  constructs `ProtectedResource`/`AccessRequest` values and asks
  `AuthorizationPolicy`; authorization never sees `SNXNode`, paths, or
  commands);
* the decision of "who acts" for a given shell (that is `SNXShell` owning an
  `ExecutionContext`).

## Relationships

* `SNXScenario.users` / `SNXScenario.groups` are the identities that exist in
  a world; the composition root builds scenario-local group membership and
  constructs the initial `ExecutionContext.for_user(user, membership)`.
* `SNXShell` owns the current `ExecutionContext` (held for the session's
  duration and mutated through the shell's interaction state); commands and
  the VFS receive it as the authorization subject.
* Filesystem ownership: `SNXNode.owner` (an `SNXUser`) and `SNXNode.group`
  (an `SNXGroup`) reference scenario-local identities — never execution
  credentials/contexts.

Consumers depend on `security/`; `security/` depends on nothing.

## Invariants

* An identity is valid only within the scenario that owns it; there is no
  global cross-scenario `SNXUser`/`SNXGroup` registry.
* A Linux identity and a SIMNUX client identity are different concepts even
  when they represent the same human.
* `user_id`/`group_id` are the numeric Linux ids; `identifier` is the Linux
  name (e.g. `"root"`). Do not use one where the other is meant.
* Commands and the VFS must never construct their own credentials from
  raw identities; credentials are built by `execution/` and held by the
  shell. Composition roots assemble credentials from scenario identity +
  membership, never ad hoc.
* Root is a scenario-local identity whose `user_id == 0`; `AuthorizationPolicy`
  treats `effective_user.user_id == 0` as privileged. There is no "client
  root".

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
* **execution credentials** — who the work runs as: real/effective identity,
  group set, reserved privilege info.
* **execution context** — the security state under which work is performed
  (the current credentials; future execution view / filesystem-root
  restriction extends here).
* **authorization** — the `security/`-owned decision of whether an execution
  context may perform an abstract requested action on a protected resource.

## Common mistakes / conflations

* Overloading `SNXUser` as a SIMNUX client account or session identity.
* Using bare strings such as `"root"` for node ownership (must be `SNXUser`
  /`SNXGroup` objects from the owning scenario).
* Letting the VFS, a command, or a shell decide authorization by reading
  permission bits itself — the VFS must ask `AuthorizationPolicy`.
* Letting the VFS/command pass a raw `SNXUser` where an `ExecutionContext` is
  required.
* Building group membership inside the VFS or per-call; membership is only
  for credential construction at the composition root.
* Naming this package "security" and then importing authentication or
  infrastructure concepts into it. Its scope is scenario-local Linux identity
  primitives plus execution/authorization abstractions; keep it a
  dependency-free leaf.

## Current-state note

`identity/` (`SNXUser`/`SNXGroup`/membership), `execution/`
(`ExecutionCredentials`/`ExecutionContext`) and `authorization/`
(`AuthorizationPolicy` + abstract request model) already match this contract.
The VFS and commands authorize via `ExecutionContext`; system-level operations
use `ExecutionContext.root()` (the scenario-local root identity). Retain
these; do not regress to passing raw `SNXUser` around or storing membership in
the VFS.