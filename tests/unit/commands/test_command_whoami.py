"""Tests for the ``whoami`` command implementation.

Covers returning the session username and rejecting unexpected arguments.
"""

import pytest

from simnux.commands.errors import CommandError
from tests.helpers import assert_invalid_args
from tests.helpers import assert_success
from tests.helpers import stderr_text
from tests.helpers import stdout_text


pytestmark = pytest.mark.asyncio


class TestWhoamiCommand:
    """Print effective user name via the ``whoami`` command.

    Uses the ``shell_with_commands`` fixture. Verifies the username
    matches the scenario's configured user and that extra arguments
    are rejected.
    """

    async def test_whoami_returns_username(self, shell_with_commands):
        """``whoami`` returns the session's username."""
        result = await shell_with_commands.execute("whoami")
        assert_success(result)
        assert stdout_text(result) == "testuser"

    async def test_whoami_with_args_rejected(self, shell_with_commands):
        """``whoami`` with arguments returns INVALID_ARGUMENT."""
        result = await shell_with_commands.execute("whoami extra")
        assert_invalid_args(result)
        assert CommandError.TOO_MANY_ARGUMENTS in stderr_text(result)
