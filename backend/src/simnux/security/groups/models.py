from dataclasses import dataclass


@dataclass(frozen=True)
class SNXGroup:
    """A SIMNUX group identity."""

    group_id: int
    identifier: str
