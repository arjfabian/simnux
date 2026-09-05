"""Central configuration for SIMNUX runtime.

The configuration value types live in ``core/runtime/config.py``; this module
owns the *loading* logic (reading ``config/limits.yaml``) and re-exports the
models for callers that traditionally imported them from ``boot.config``.
"""

from __future__ import annotations

import logging
from pathlib import Path

from simnux.core.runtime.config import LimitsConfig
from simnux.core.runtime.config import RuntimeConfig
from simnux.core.runtime.config import ScriptLimits
from simnux.core.runtime.config import VfsLimits


__all__ = [
    "LimitsConfig",
    "RuntimeConfig",
    "ScriptLimits",
    "VfsLimits",
    "load_limits_config",
]


logger = logging.getLogger("simnux.config")


def load_limits_config(project_root: Path | None = None) -> LimitsConfig:
    """Read ``config/limits.yaml`` and return a validated ``LimitsConfig``.

    Falls back to built-in defaults when the file is absent, empty, or
    contains invalid YAML.
    """
    if project_root is None:
        # Walk up from boot/config.py -> boot -> simnux -> src -> backend -> project_root
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
