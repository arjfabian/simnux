"""The single authority for execution-authorization policy.

Owns the semantics of "is this execution context authorized for this abstract
requested action?":

* Unix class selection: the resource owner matches the owner tier
  (``permissions.user``), then a member of the resource's group matches the
  group tier (``permissions.group``), then everyone else matches the other
  tier (``permissions.other``). Classes are never combined.
* Privilege bypass: an execution whose *effective* identity is ``user_id == 0``
  bypasses class-based checks (the documented root policy). No general
  privileged-process mechanism (sudo, setuid) exists yet; the ``privileges``
  credential field is reserved for it.

The policy is immutable, dependency-free, and filesystem-independent: it never
imports nodes, paths, commands, shells, sessions, or the VFS. The filesystem is
one consumer; any credential-gated subsystem may use it.
"""

from __future__ import annotations

from simnux.security.authorization.models import Access
from simnux.security.authorization.models import AccessRequest
from simnux.security.authorization.models import PermissionFlags
from simnux.security.authorization.models import ProtectedResource
from simnux.security.execution.models import ExecutionContext


_ACCESS_FLAG = {
    Access.READ: "read",
    Access.WRITE: "write",
    Access.EXECUTE: "execute",
}


def _is_privileged(context: ExecutionContext) -> bool:
    """The documented root policy: effective ``user_id == 0`` bypasses checks."""
    return context.credentials.effective_user.user_id == 0


class AuthorizationPolicy:
    """Immutable allow/deny policy for execution contexts."""

    def authorize(self, request: AccessRequest) -> bool:
        """Return True when *request.subject* may perform *request.right* on
        *request.resource*."""
        if _is_privileged(request.subject):
            return True
        flags = self.flags_for(request.subject, request.resource)
        return bool(getattr(flags, _ACCESS_FLAG[request.right]))

    def flags_for(
        self,
        context: ExecutionContext,
        resource: ProtectedResource,
    ) -> PermissionFlags:
        """Owner -> user bits; group member -> group bits; else other bits."""
        effective = context.credentials.effective_user
        if resource.owner.user_id == effective.user_id:
            return resource.permissions.user
        if any(group.group_id == resource.group.group_id for group in context.credentials.groups):
            return resource.permissions.group
        return resource.permissions.other

    def is_owner(
        self,
        context: ExecutionContext,
        resource: ProtectedResource,
    ) -> bool:
        """True when the effective identity owns *resource* (owner-or-root
        gates such as ``chmod`` use this with :meth:`is_privileged`)."""
        return context.credentials.effective_user.user_id == resource.owner.user_id

    def is_privileged(self, context: ExecutionContext) -> bool:
        """True when the execution bypasses class-based checks."""
        return _is_privileged(context)
