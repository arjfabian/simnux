"""Central configuration for SIMNUX runtime."""

from __future__ import annotations

import logging
from pathlib import Path

from pydantic import BaseModel


logger = logging.getLogger("simnux.config")


# ── Limits configuration ─────────────────────────────────────────────────


class VfsLimits(BaseModel):
    """Per-session VFS byte caps."""

    max_file_bytes: int = 1_048_576  # 1 MB
    max_total_bytes: int = 10_485_760  # 10 MB


class ScriptLimits(BaseModel):
    """Bounds for script execution."""

    max_loop_iterations: int = 10_000
    max_execution_time_seconds: int = 30
    max_lines: int = 5_000


class LimitsConfig(BaseModel):
    """Resource limits for the SIMNUX runtime.

    Loaded from ``config/limits.yaml`` with safe defaults for every field.
    If the file is missing or partially filled, the defaults apply.
    """

    vfs: VfsLimits = VfsLimits()
    script: ScriptLimits = ScriptLimits()


def load_limits_config(project_root: Path | None = None) -> LimitsConfig:
    """Read ``config/limits.yaml`` and return a validated ``LimitsConfig``.

    Falls back to built-in defaults when the file is absent, empty, or
    contains invalid YAML.
    """
    if project_root is None:
        # Walk up from this file: init/config.py -> init -> simnux -> src -> backend -> project_root
        project_root = Path(__file__).resolve().parent.parent.parent.parent.parent

    config_path = project_root / "config" / "limits.yaml"

    if not config_path.exists():
        logger.debug("No limits.yaml found — using defaults")
        return LimitsConfig()

    try:
        import yaml

        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception:
        logger.warning("Failed to parse limits.yaml — using defaults", exc_info=True)
        return LimitsConfig()

    return LimitsConfig.model_validate(raw)


# ── Runtime configuration ────────────────────────────────────────────────


class RuntimeConfig(BaseModel):
    """Runtime configuration for logging path and debug mode.

    Intentionally small — most behavioral variation comes from scenario
    definitions, not runtime config.
    """

    log_path: str = "/tmp/simnux.log"
    debug: bool = False
