"""Well-known error message constants for command-level diagnostics.

Maps to Linux coreutils error strings for compatibility.
"""

from enum import Enum


class CommandError(str, Enum):
    """Stable command error strings."""

    COMMAND_NOT_FOUND = "command not found"
    DIRECTORY_NOT_EMPTY = "directory not empty"
    FILE_EXISTS = "file exists"
    IS_A_DIRECTORY = "is a directory"
    MISSING_FILE_OPERAND = "missing file operand"
    MISSING_OPERAND = "missing operand"
    NO_SUCH_FILE_OR_DIR = "no such file or directory"
    NOT_A_DIRECTORY = "not a directory"
    NOT_FOUND = "not found"
    TOO_MANY_ARGUMENTS = "too many arguments"

    def __str__(self):
        return self.value
