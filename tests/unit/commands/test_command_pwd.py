"""Tests for the ``pwd`` command implementation.

Covers returning the current working directory, reflecting ``cd``
mutations, and rejecting unexpected arguments.
"""

from simnux.commands.errors import CommandError

from tests.helpers import (
    assert_invalid_args,
    assert_success,
    stderr_text,
    stdout_text,
) 

class TestPwdCommand:
    """Print working directory via the ``pwd`` command.

    Uses the ``shell_with_commands`` fixture. Verifies initial CWD,
    updates after ``cd``, and argument rejection.
    """

    def test_pwd_returns_cwd(self, shell_with_commands):
        """``pwd`` returns the session's current working directory."""
        result = shell_with_commands.execute("pwd")
        assert_success(result)
        assert stdout_text(result) == "/home/user"

    def test_pwd_after_cd(self, shell_with_commands):
        """``pwd`` reflects the CWD after a ``cd`` mutation."""
        shell_with_commands.execute("cd /etc")

        result = shell_with_commands.execute("pwd")
        
        assert stdout_text(result) == "/etc"

    def test_pwd_with_args_rejected(self, shell_with_commands):
        """``pwd`` with arguments returns INVALID_ARGUMENT (TOO_MANY_ARGUMENTS)."""
        result = shell_with_commands.execute("pwd /etc")
        assert_invalid_args(result)
        assert CommandError.TOO_MANY_ARGUMENTS in stderr_text(result)
