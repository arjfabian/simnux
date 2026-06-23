"""Tests for unknown/unregistered command handling.

Verifies that executing a command not present in the registry returns
a ``COMMAND_NOT_FOUND`` error.
"""

from tests.helpers import assert_error
from tests.helpers import stderr_text

from simnux.commands.errors import CommandError


class TestUnknownCommand:
    """Handler for commands not present in the registry.

    Uses the ``shell_with_commands`` fixture. Verifies that executing
    an unregistered command produces a ``COMMAND_NOT_FOUND`` error
    rather than crashing.
    """

    def test_unknown_command(self, shell_with_commands):
        """Executing an unregistered command returns ERROR with COMMAND_NOT_FOUND."""
        result = shell_with_commands.execute("nonexistent")
        assert_error(result)
        assert CommandError.COMMAND_NOT_FOUND in stderr_text(result)
