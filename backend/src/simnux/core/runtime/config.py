"""Core runtime configuration models for SIMNUX.

Value types used by the runtime/command layers. Loading and validation of
runtime configuration lives in ``boot/config.py`` (the composition root);
core only defines the shapes.
"""

from __future__ import annotations

from pydantic import BaseModel


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


# ── Runtime configuration ────────────────────────────────────────────────


class RuntimeConfig(BaseModel):
    """Runtime configuration for logging path and debug mode.

    Intentionally small — most behavioral variation comes from scenario
    definitions, not runtime config.
    """

    log_path: str = "/tmp/simnux.log"
    debug: bool = False
