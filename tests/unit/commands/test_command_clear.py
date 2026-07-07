"""Tests for the ``clear`` command implementation.

Covers clearing the terminal screen signal and rejecting unexpected
arguments.
"""

import pytest

from simnux.commands.errors import CommandError
from tests.helpers import assert_invalid_args
from tests.helpers import assert_success
from tests.helpers import stderr_text


pytestmark = pytest.mark.asyncio


class TestClearCommand:
    """Terminal screen clearing via the ``clear`` command.

    Uses the ``shell_with_commands`` fixture. Verifies the
    ``clear_screen`` flag is set and that extra arguments are
    rejected.
    """

    async def test_clear_sets_flag(self, shell_with_commands):
        """``clear`` returns SUCCESS with ``clear_screen`` set to True."""
        result = await shell_with_commands.execute("clear")
        assert_success(result)
        assert result.clear_screen is True
        assert result.stdout == []
        assert result.stderr == []

    async def test_clear_rejects_args(self, shell_with_commands):
        """``clear`` with arguments returns INVALID_ARGUMENT."""
        result = await shell_with_commands.execute("clear extra")
        assert_invalid_args(result)
        assert CommandError.TOO_MANY_ARGUMENTS in stderr_text(result)
        assert result.clear_screen is False
