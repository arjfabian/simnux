"""Pure renderers for the ``/etc`` account-file projections.

These functions derive the ``/etc/passwd``, ``/etc/group``, and
``/etc/shadow`` file contents from the authoritative scenario identity state
(exposed through :class:`~simnux.core.scenarios.identity.IdentityManager`).
They are pure data transformations: rendering never touches the filesystem —
applying the rendered content into a shell's VFS belongs to
``SNXShell.refresh_account_files`` (``core/shell/``).

``IdentityState`` remains the sole authority for identities, membership, and
primary-group relationships; the rendered files are derived representations
only and never a second identity database. ``/etc/shadow`` is derived except
for the password/aging fields, which live only in the file: ``render_shadow``
therefore merges with the existing file content, preserving those fields
verbatim for users that still exist and emitting locked (``!``) entries for
newly created users.
"""

from __future__ import annotations

from collections.abc import Iterable

from simnux.security.groups.models import SNXGroup
from simnux.security.users.models import SNXUser


_LOCKED_SHADOW_LINE = "!:20000:0:99999:7:::"


def render_passwd(
    users: Iterable[SNXUser],
    groups: Iterable[SNXGroup],
) -> str:
    """Render ``/etc/passwd`` content for the given scenario users/groups.

    The password field is always ``x`` (credentials live in
    ``/etc/shadow``). Each non-root user maps to its same-named primary group
    id (falling back to its uid when no such group is registered), its
    scenario-local home directory, and a deterministic default shell.
    """
    users = list(users)
    groups_by_identifier = {group.identifier: group for group in groups}

    entries = ["root:x:0:0:root:/root:/bin/sh"]

    for user in users:
        if user.identifier == "root":
            continue

        group = groups_by_identifier.get(user.identifier)
        gid = group.group_id if group is not None else user.user_id

        entries.append(
            f"{user.identifier}:x:{user.user_id}:{gid}:{user.identifier}:"
            f"/home/{user.identifier}:/bin/sh"
        )

    return "\n".join(entries) + "\n"


def render_group(users: Iterable[SNXUser]) -> str:
    """Render ``/etc/group`` content for the given scenario users.

    Follows the bootstrap convention: one same-named group per user with
    ``gid == uid`` and the user as its sole listed member.
    """
    users = list(users)

    entries = ["root:x:0:root"]

    for user in users:
        if user.identifier == "root":
            continue

        entries.append(f"{user.identifier}:x:{user.user_id}:{user.identifier}")

    return "\n".join(entries) + "\n"


def render_shadow(
    users: Iterable[SNXUser],
    existing_content: str | None = None,
) -> str:
    """Render ``/etc/shadow`` content, preserving existing password fields.

    For every current scenario user, the line from *existing_content* (keyed
    by user identifier) is kept verbatim when present — including credential
    and aging fields written by ``passwd`` — otherwise a locked (``!``) entry
    with the bootstrap aging defaults is emitted. Lines for identities that no
    longer exist in the authoritative state are dropped. Renders all-locked
    content when *existing_content* is ``None``/empty (the bootstrap case).
    """
    existing_by_identifier: dict[str, str] = {}
    for line in (existing_content or "").splitlines():
        if not line:
            continue
        existing_by_identifier[line.split(":", 1)[0]] = line

    entries: list[str] = []
    for user in users:
        existing = existing_by_identifier.get(user.identifier)
        if existing is not None:
            entries.append(existing)
        else:
            entries.append(f"{user.identifier}:{_LOCKED_SHADOW_LINE}")

    return "\n".join(entries) + "\n"
