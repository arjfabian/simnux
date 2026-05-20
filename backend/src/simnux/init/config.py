"""Central configuration for SIMNUX runtime."""

from dataclasses import dataclass


@dataclass
class RuntimeConfig:
    """Runtime configuration for logging path and debug mode.

    Intentionally small — most behavioral variation comes from scenario
    definitions, not runtime config.
    """

    log_path: str = "/tmp/simnux.log"
    debug: bool = False
