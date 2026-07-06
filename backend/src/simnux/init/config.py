"""Central configuration for SIMNUX runtime."""

from pydantic import BaseModel


class RuntimeConfig(BaseModel):
    """Runtime configuration for logging path and debug mode.

    Intentionally small — most behavioral variation comes from scenario
    definitions, not runtime config.
    """

    log_path: str = "/tmp/simnux.log"
    debug: bool = False
