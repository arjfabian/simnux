"""Tests for unknown/unregistered command handling.

Verifies that executing a command not present in the registry returns
a ``COMMAND_NOT_FOUND`` error.
"""

import pytest

from simnux.core.commands.errors import CommandError
from tests.helpers import assert_error
from tests.helpers import stderr_text


pytestmark = pytest.mark.asyncio


class TestUnknownCommand:
    """Handler for commands not present in the registry.

    Uses the ``shell_with_commands`` fixture. Verifies that executing
    an unregistered command produces a ``COMMAND_NOT_FOUND`` error
    rather than crashing.
    """

    async def test_unknown_command(self, shell_with_commands):
        """Executing an unregistered command returns ERROR with COMMAND_NOT_FOUND."""
        result = await shell_with_commands.execute("nonexistent")
        assert_error(result)
        assert CommandError.COMMAND_NOT_FOUND in stderr_text(result)
