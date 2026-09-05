"""Scenario domain models for SIMNUX."""

from typing import Any

from pydantic import BaseModel

from simnux.core.filesystem.models import SNXNode
from simnux.security.groups.models import SNXGroup
from simnux.security.users.models import SNXUser


class SNXScenario(BaseModel):
    """Normalized in-memory representation of a loaded scenario.

    Populated by ``ScenarioLoader`` from YAML. All filesystem paths in
    ``filesystem`` dict are absolute keys to ``SNXNode`` objects.
    """

    name: str
    difficulty: str

    hostname: str

    groups: dict[str, SNXGroup]
    users: dict[str, SNXUser]

    starting_dir: str
    filesystem: dict[str, SNXNode]

    objective: dict[str, Any] | None = None
    triggers: list[dict[str, Any]] | None = None
