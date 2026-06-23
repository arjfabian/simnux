"""Shell-level command parsing models for SIMNUX."""

from dataclasses import dataclass


@dataclass
class ParsedCommand:
    command: str
    args: list[str]
