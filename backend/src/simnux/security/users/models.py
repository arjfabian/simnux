from dataclasses import dataclass


@dataclass(frozen=True)
class SNXUser:
    """A SIMNUX user identity."""

    user_id: int
    identifier: str
