"""Tests for the ``diff`` command."""

from __future__ import annotations

import pytest

from simnux.core.commands.errors import CommandError
from tests.helpers import assert_error
from tests.helpers import assert_invalid_args
from tests.helpers import assert_success
from tests.helpers import stderr_text
from tests.helpers import stdout_text


pytestmark = pytest.mark.asyncio


A_CONTENT = """apple
banana
cherry
date
"""

B_CONTENT = """apple
banana
cherry
elderberry
fig
"""

SINGLE_A = "line1"
SINGLE_B = "line2"


class TestDiffCommand:
    """File comparison via the ``diff`` command."""

    async def _write(self, shell, path, content):
        shell.filesystem.touch(path, acting_user=shell.user)
        shell.filesystem.delta_layer[path].content = content

    # -- basic diff ---------------------------------------------------------

    async def test_diff_different_files(self, shell_with_commands):
        """``diff`` on differing files returns exit code 1 (ERROR)."""
        await self._write(shell_with_commands, "/home/user/a.txt", A_CONTENT)
        await self._write(shell_with_commands, "/home/user/b.txt", B_CONTENT)
        result = await shell_with_commands.execute("diff /home/user/a.txt /home/user/b.txt")
        assert_error(result)
        stdout = stdout_text(result)
        assert "---" in stdout
        assert "+++" in stdout
        assert "-date" in stdout
        assert "+elderberry" in stdout
        assert "+fig" in stdout

    async def test_diff_identical_files(self, shell_with_commands):
        """``diff`` on identical files returns exit code 0 (SUCCESS)."""
        await self._write(shell_with_commands, "/home/user/a.txt", A_CONTENT)
        await self._write(shell_with_commands, "/home/user/b.txt", A_CONTENT)
        result = await shell_with_commands.execute("diff /home/user/a.txt /home/user/b.txt")
        assert_success(result)
        assert stdout_text(result) == ""

    async def test_diff_empty_files(self, shell_with_commands):
        """``diff`` on two empty files returns exit code 0."""
        shell_with_commands.filesystem.touch(
            "/home/user/empty1", acting_user=shell_with_commands.user
        )
        shell_with_commands.filesystem.touch(
            "/home/user/empty2", acting_user=shell_with_commands.user
        )
        result = await shell_with_commands.execute("diff /home/user/empty1 /home/user/empty2")
        assert_success(result)
        assert stdout_text(result) == ""

    async def test_diff_file_labels_in_header(self, shell_with_commands):
        """The diff header shows the original file names, not resolved paths."""
        await self._write(shell_with_commands, "/home/user/a.txt", "line1\n")
        await self._write(shell_with_commands, "/home/user/b.txt", "line2\n")
        result = await shell_with_commands.execute("diff /home/user/a.txt /home/user/b.txt")
        assert_error(result)
        stdout = stdout_text(result)
        assert "/home/user/a.txt" in stdout
        assert "/home/user/b.txt" in stdout

    # -- stdin "-" operator -------------------------------------------------

    async def test_diff_stdin_on_right(self, shell_with_commands):
        """``diff file -`` compares file against stdin."""
        await self._write(shell_with_commands, "/home/user/a.txt", SINGLE_A)
        result = await shell_with_commands.execute("echo line1 | diff /home/user/a.txt -")
        assert_success(result)
        assert stdout_text(result) == ""

    async def test_diff_stdin_on_right_different(self, shell_with_commands):
        """``diff file -`` detects differences from stdin."""
        await self._write(shell_with_commands, "/home/user/a.txt", SINGLE_A)
        result = await shell_with_commands.execute("echo line2 | diff /home/user/a.txt -")
        assert_error(result)
        assert "-line1" in stdout_text(result)

    async def test_diff_stdin_on_left(self, shell_with_commands):
        """``diff - file`` compares stdin against file."""
        await self._write(shell_with_commands, "/home/user/b.txt", SINGLE_B)
        result = await shell_with_commands.execute("echo line2 | diff - /home/user/b.txt")
        assert_success(result)
        assert stdout_text(result) == ""

    async def test_diff_stdin_both_sides(self, shell_with_commands):
        """``diff - -`` compares stdin against itself (no diff)."""
        result = await shell_with_commands.execute("echo hello | diff - -")
        assert_success(result)
        assert stdout_text(result) == ""

    # -- errors -------------------------------------------------------------

    async def test_diff_no_args(self, shell_with_commands):
        """``diff`` with no args returns INVALID_ARGUMENT."""
        result = await shell_with_commands.execute("diff")
        assert_invalid_args(result)
        assert CommandError.MISSING_OPERAND in stderr_text(result)

    async def test_diff_one_arg(self, shell_with_commands):
        """``diff`` with one arg returns INVALID_ARGUMENT."""
        result = await shell_with_commands.execute("diff /home/user/a.txt")
        assert_invalid_args(result)
        assert CommandError.MISSING_OPERAND in stderr_text(result)

    async def test_diff_three_args(self, shell_with_commands):
        """``diff`` with three args returns INVALID_ARGUMENT."""
        result = await shell_with_commands.execute("diff a.txt b.txt c.txt")
        assert_invalid_args(result)
        assert CommandError.TOO_MANY_ARGUMENTS in stderr_text(result)

    async def test_diff_nonexistent_file(self, shell_with_commands):
        """``diff`` on a nonexistent file returns ERROR."""
        await self._write(shell_with_commands, "/home/user/a.txt", "hello\n")
        result = await shell_with_commands.execute("diff /home/user/a.txt /nonexistent")
        assert_error(result)
        assert "not found" in stderr_text(result)

    async def test_diff_directory_target(self, shell_with_commands):
        """``diff`` with a directory target returns ERROR with IS_A_DIRECTORY."""
        await self._write(shell_with_commands, "/home/user/a.txt", "hello\n")
        result = await shell_with_commands.execute("diff /home/user/a.txt /home")
        assert_error(result)
        assert "is a directory" in stderr_text(result)
