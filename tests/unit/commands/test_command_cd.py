"""Tests for the ``cd`` command implementation.

Covers navigation to existing directories, nonexistent paths, file
targets (rejected), home directory fallback (no args / tilde), and
argument validation.
"""

import pytest

from simnux.commands.errors import CommandError
from tests.helpers import assert_error
from tests.helpers import assert_invalid_args
from tests.helpers import assert_success
from tests.helpers import stderr_text


pytestmark = pytest.mark.asyncio

# TODO: This is a hardcoded Home Directory path. When SNXUser is implemented,
# the Home Directory will be read from the default Scenario values.
TEST_HOME = "/home/user"


class TestCdCommand:
    """Directory navigation via the ``cd`` command.

    Uses the ``shell_with_commands`` fixture. Verifies CWD changes,
    error handling for invalid targets, home-directory fallback
    (no args or tilde), and argument count validation.
    """

    async def test_cd_to_existing_directory(self, shell_with_commands):
        """Cd to an existing directory updates the session's CWD."""
        result = await shell_with_commands.execute("cd /etc")
        assert_success(result)
        assert shell_with_commands.session.current_directory == "/etc"

    async def test_cd_to_nonexistent(self, shell_with_commands):
        """Cd to a nonexistent path returns ERROR with NO_SUCH_FILE_OR_DIR."""
        result = await shell_with_commands.execute("cd /nonexistent")
        assert_error(result)
        assert CommandError.NO_SUCH_FILE_OR_DIR in stderr_text(result)

    async def test_cd_to_file(self, shell_with_commands):
        """Cd to a file path returns ERROR with NOT_A_DIRECTORY."""
        result = await shell_with_commands.execute("cd /etc/hostname")
        assert_error(result)
        assert CommandError.NOT_A_DIRECTORY in stderr_text(result)

    async def test_cd_with_no_args_goes_home(self, shell_with_commands):
        """Cd with no arguments returns to the user's home directory."""
        shell_with_commands.session.set_cwd("/etc")
        result = await shell_with_commands.execute("cd")
        assert_success(result)
        assert shell_with_commands.session.current_directory == TEST_HOME

    async def test_cd_with_tilde(self, shell_with_commands):
        """``cd ~`` resolves to the home directory."""
        shell_with_commands.session.set_cwd("/tmp")
        result = await shell_with_commands.execute("cd ~")
        assert_success(result)
        assert shell_with_commands.session.current_directory == TEST_HOME

    async def test_cd_too_many_args(self, shell_with_commands):
        """Cd with more than one argument returns INVALID_ARGUMENT."""
        result = await shell_with_commands.execute("cd /etc /tmp")
        assert_invalid_args(result)
        assert CommandError.TOO_MANY_ARGUMENTS in stderr_text(result)
