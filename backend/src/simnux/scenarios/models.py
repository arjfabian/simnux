"""Scenario domain models for SIMNUX."""

from typing import Any

from pydantic import BaseModel

from simnux.filesystem.models import SNXNode


class SNXScenario(BaseModel):
    """Normalized in-memory representation of a loaded scenario.

    Populated by ``ScenarioLoader`` from YAML. All filesystem paths in
    ``filesystem`` dict are absolute keys to ``SNXNode`` objects.
    """

    name: str
    difficulty: str

    username: str
    hostname: str
    starting_dir: str

    filesystem: dict[str, SNXNode]

    objective: dict[str, Any] | None = None
    triggers: list[dict[str, Any]] | None = None
