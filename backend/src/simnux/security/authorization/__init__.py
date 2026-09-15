"""Authorization domain: access requests, permission profiles, and the
abstract protected resources the filesystem (and any credential-gated
consumer) asks about.

Authorization must not import sessions, shells, scenarios, paths, commands,
or the filesystem/VFS. The VFS constructs the neutral
:class:`ProtectedResource` descriptors used here and asks the policy whether a
:class:`~simnux.security.execution.models.ExecutionContext` may perform a
given :class:`AccessRight` on them.
"""

from .models import Access
from .models import AccessRequest
from .models import PermissionFlags
from .models import ProtectedResource
from .models import SNXPermissions
from .policy import AuthorizationPolicy


__all__ = [
    "Access",
    "AccessRequest",
    "AuthorizationPolicy",
    "PermissionFlags",
    "ProtectedResource",
    "SNXPermissions",
]
