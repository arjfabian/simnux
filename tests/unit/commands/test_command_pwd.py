"""Tests for the ``pwd`` command implementation.

Covers returning the current working directory, reflecting ``cd``
mutations, and rejecting unexpected arguments.
"""

import pytest

from simnux.commands.errors import CommandError
from tests.helpers import assert_invalid_args
from tests.helpers import assert_success
from tests.helpers import stderr_text
from tests.helpers import stdout_text


pytestmark = pytest.mark.asyncio


class TestPwdCommand:
    """Print working directory via the ``pwd`` command.

    Uses the ``shell_with_commands`` fixture. Verifies initial CWD,
    updates after ``cd``, and argument rejection.
    """

    async def test_pwd_returns_cwd(self, shell_with_commands):
        """``pwd`` returns the session's current working directory."""
        result = await shell_with_commands.execute("pwd")
        assert_success(result)
        assert stdout_text(result) == "/home/user"

    async def test_pwd_after_cd(self, shell_with_commands):
        """``pwd`` reflects the CWD after a ``cd`` mutation."""
        await shell_with_commands.execute("cd /etc")

        result = await shell_with_commands.execute("pwd")

        assert stdout_text(result) == "/etc"

    async def test_pwd_with_args_rejected(self, shell_with_commands):
        """``pwd`` with arguments returns INVALID_ARGUMENT (TOO_MANY_ARGUMENTS)."""
        result = await shell_with_commands.execute("pwd /etc")
        assert_invalid_args(result)
        assert CommandError.TOO_MANY_ARGUMENTS in stderr_text(result)
