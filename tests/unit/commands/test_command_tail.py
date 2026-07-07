"""Tests for the ``tail`` command."""

import pytest

from simnux.commands.errors import CommandError
from tests.helpers import assert_error
from tests.helpers import assert_invalid_args
from tests.helpers import assert_success
from tests.helpers import stderr_text
from tests.helpers import stdout_text


pytestmark = pytest.mark.asyncio


MULTI_LINE = "\n".join(f"line {i}" for i in range(1, 21))  # 20 lines


class TestTailCommand:
    """Shell-level integration tests for tail."""

    async def _write_multi(self, shell, path="/home/user/multi.txt"):
        shell.filesystem.touch(path)
        shell.filesystem.delta_layer[path].content = MULTI_LINE

    # -- basic file reading ------------------------------------------------

    async def test_tail_default_n(self, shell_with_commands):
        """``tail`` without -n outputs the last 10 lines."""
        await self._write_multi(shell_with_commands)
        result = await shell_with_commands.execute("tail /home/user/multi.txt")
        assert_success(result)
        assert stdout_text(result) == "\n".join(f"line {i}" for i in range(11, 21))

    async def test_tail_custom_n(self, shell_with_commands):
        """``tail -n 5`` outputs the last 5 lines."""
        await self._write_multi(shell_with_commands)
        result = await shell_with_commands.execute("tail -n 5 /home/user/multi.txt")
        assert_success(result)
        assert stdout_text(result) == "\n".join(f"line {i}" for i in range(16, 21))

    async def test_tail_shorthand(self, shell_with_commands):
        """``tail -3`` expands to ``tail -n 3``."""
        await self._write_multi(shell_with_commands)
        result = await shell_with_commands.execute("tail -3 /home/user/multi.txt")
        assert_success(result)
        assert stdout_text(result) == "\n".join(f"line {i}" for i in range(18, 21))

    async def test_tail_long_option(self, shell_with_commands):
        """``tail --lines=7`` outputs the last 7 lines."""
        await self._write_multi(shell_with_commands)
        result = await shell_with_commands.execute(
            "tail --lines=7 /home/user/multi.txt"
        )
        assert_success(result)
        assert stdout_text(result) == "\n".join(f"line {i}" for i in range(14, 21))

    # -- stdin fallback ----------------------------------------------------

    async def test_tail_stdin_pipe(self, shell_with_commands):
        """``tail`` with no file reads from stdin."""
        await self._write_multi(shell_with_commands)
        result = await shell_with_commands.execute(
            "cat /home/user/multi.txt | tail"
        )
        assert_success(result)
        assert stdout_text(result) == "\n".join(f"line {i}" for i in range(11, 21))

    async def test_tail_stdin_with_n(self, shell_with_commands):
        """``tail -n 3`` reads from stdin with custom count."""
        shell_with_commands.filesystem.touch("/home/user/data.txt")
        shell_with_commands.filesystem.delta_layer["/home/user/data.txt"].content = "hello\nworld\nfoo\nbar\nbaz"
        result = await shell_with_commands.execute(
            "cat /home/user/data.txt | tail -n 3"
        )
        assert_success(result)
        assert stdout_text(result) == "foo\nbar\nbaz"

    # -- edge cases --------------------------------------------------------

    async def test_tail_file_shorter_than_n(self, shell_with_commands):
        """File with fewer lines than N outputs all lines."""
        shell_with_commands.filesystem.touch("/home/user/short.txt")
        shell_with_commands.filesystem.delta_layer["/home/user/short.txt"].content = "only\nthree\nlines"
        result = await shell_with_commands.execute(
            "tail -n 50 /home/user/short.txt"
        )
        assert_success(result)
        assert stdout_text(result) == "only\nthree\nlines"

    async def test_tail_n_zero(self, shell_with_commands):
        """``tail -n 0`` outputs nothing."""
        await self._write_multi(shell_with_commands)
        result = await shell_with_commands.execute("tail -n 0 /home/user/multi.txt")
        assert_success(result)
        assert stdout_text(result) == ""

    # -- errors ------------------------------------------------------------

    async def test_tail_missing_file(self, shell_with_commands):
        """``tail`` on a nonexistent file returns ERROR."""
        result = await shell_with_commands.execute("tail /nonexistent")
        assert_error(result)
        assert CommandError.NOT_FOUND in stderr_text(result)

    async def test_tail_is_directory(self, shell_with_commands):
        """``tail`` on a directory returns ERROR with IS_A_DIRECTORY."""
        result = await shell_with_commands.execute("tail /home")
        assert_error(result)
        assert CommandError.IS_A_DIRECTORY in stderr_text(result)

    async def test_tail_invalid_n_value(self, shell_with_commands):
        """``tail -n abc`` returns INVALID_ARGUMENT with GNU error message."""
        await self._write_multi(shell_with_commands)
        result = await shell_with_commands.execute("tail -n abc /home/user/multi.txt")
        assert_invalid_args(result)
        assert "tail: invalid number of lines: 'abc'" in stderr_text(result)
