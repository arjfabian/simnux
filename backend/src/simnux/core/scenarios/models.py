"""Scenario domain models for SIMNUX."""

from typing import Any

from pydantic import BaseModel
from pydantic import Field

from simnux.core.filesystem.models import SNXNode
from simnux.security.groups.models import SNXGroup
from simnux.security.users.models import SNXUser

from .identity import IdentityState


class SNXScenario(BaseModel):
    """Normalized in-memory representation of a loaded scenario.

    Populated by ``ScenarioLoader`` from YAML. All filesystem paths in
    ``filesystem`` dict are absolute keys to ``SNXNode`` objects.

    Identities: ``identity_state`` (an ``IdentityState``) is the authoritative
    mutable source of truth for users, groups, membership, and primary-group
    relationships. ``users``/``groups`` are retained as declarative
    projections of the loaded scenario for compatibility (filesystem-ownership
    bootstrap, account-file rendering, display). The loader keeps them
    consistent with the seeded ``identity_state`` at load time; new identity
    management flows must mutate ``identity_state`` (via ``IdentityManager``),
    never these dicts.
    """

    name: str
    difficulty: str

    hostname: str

    groups: dict[str, SNXGroup]
    users: dict[str, SNXUser]

    identity_state: IdentityState = Field(default_factory=IdentityState)

    starting_dir: str
    filesystem: dict[str, SNXNode]

    objective: dict[str, Any] | None = None
    triggers: list[dict[str, Any]] | None = None
