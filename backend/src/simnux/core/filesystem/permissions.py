"""The single authoritative Unix-style permission evaluator for the VFS.

Permission decisions live in exactly one place: the filesystem layer, via
:class:`PermissionEvaluator`. Commands route every permission-sensitive
inspection/mutation through the VFS, which consults this evaluator; commands
never implement their own Unix permission logic, and the shell/session never
decides file access.

Policy
------
* The acting user is the scenario-local ``SNXUser`` owning the current
  interaction (shell state) — never a SIMNUX session or client identity.
* ``root`` (``user_id == 0``) bypasses all checks: a deliberate, explicit
  policy. No general privileged-process framework (sudo, setuid) exists yet.
* Otherwise class selection follows Unix: the node owner is matched first
  (``permissions.user``), then a member of the node's group
  (``permissions.group``), then everyone else (``permissions.other``).
  Classes are never combined.
* Group membership comes from the scenario-scoped ``SNXGroupMembership``
  injected at the composition root; a node stores its group as an
  ``SNXGroup`` and the evaluator only ever compares ``group_id`` values.
"""

from __future__ import annotations

from enum import Enum

from simnux.core.filesystem.models import SNXNode
from simnux.security.groups.membership import SNXGroupMembership
from simnux.security.users.models import SNXUser


class Access(Enum):
    """Kinds of access the VFS can gate on."""

    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"


_ACCESS_FLAG = {
    Access.READ: "read",
    Access.WRITE: "write",
    Access.EXECUTE: "execute",
}


class PermissionEvaluator:
    """Allow/deny decision maker for VFS access.

    Immutable and dependency-free beyond the injected membership view, so it
    can be exercised directly in unit tests.
    """

    def __init__(self, membership: SNXGroupMembership) -> None:
        self._membership = membership

    def check(self, user: SNXUser, node: SNXNode, access: Access) -> bool:
        """Return True when *user* may perform *access* on *node*."""
        if user.user_id == 0:
            return True
        flags = self._flags_for(user, node)
        return bool(getattr(flags, _ACCESS_FLAG[access]))

    def _flags_for(self, user: SNXUser, node: SNXNode):
        """Owner -> user bits; group member -> group bits; else other bits."""
        if node.owner.user_id == user.user_id:
            return node.permissions.user
        if self._membership.is_member(user.user_id, node.group.group_id):
            return node.permissions.group
        return node.permissions.other
