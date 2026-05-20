"""Well-known error message constants for command-level diagnostics.

Maps to Linux coreutils error strings for compatibility.
"""

from enum import Enum


class CommandError(str, Enum):
    """Stable command error strings."""

    MISSING_FILE_OPERAND = "missing file operand"
    MISSING_OPERAND = "missing operand"
    TOO_MANY_ARGUMENTS = "too many arguments"
