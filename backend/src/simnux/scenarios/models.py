"""Scenario domain models for SIMNUX."""

from pydantic import BaseModel

from simnux.filesystem.models import SNXNode


class SNXScenario(BaseModel):
    """Normalized in-memory representation of a loaded scenario.

    Populated by ``ScenarioLoader`` from YAML. All filesystem paths in
    ``filesystem`` dict are absolute keys to ``SNXNode`` objects.
    """

    name: str
    motd: str
    difficulty: str

    username: str
    hostname: str
    starting_dir: str

    filesystem: dict[str, SNXNode]
