"""Tests for the ``head`` command."""

import pytest

from simnux.core.commands.errors import CommandError
from tests.helpers import assert_error
from tests.helpers import assert_invalid_args
from tests.helpers import assert_success
from tests.helpers import stderr_text
from tests.helpers import stdout_text


pytestmark = pytest.mark.asyncio


MULTI_LINE = "\n".join(f"line {i}" for i in range(1, 21))  # 20 lines


class TestHeadCommand:
    """Shell-level integration tests for head."""

    async def _write_multi(self, shell, path="/home/user/multi.txt"):
        shell.filesystem.touch(path, acting_user=shell.user)
        shell.filesystem.delta_layer[path].content = MULTI_LINE

    async def _write(self, shell, path, content):
        shell.filesystem.touch(path, acting_user=shell.user)
        shell.filesystem.delta_layer[path].content = content

    # -- basic file reading ------------------------------------------------

    async def test_head_default_n(self, shell_with_commands):
        """``head`` without -n outputs the first 10 lines."""
        await self._write_multi(shell_with_commands)
        result = await shell_with_commands.execute("head /home/user/multi.txt")
        assert_success(result)
        assert stdout_text(result) == "\n".join(f"line {i}" for i in range(1, 11))

    async def test_head_custom_n(self, shell_with_commands):
        """``head -n 5`` outputs the first 5 lines."""
        await self._write_multi(shell_with_commands)
        result = await shell_with_commands.execute("head -n 5 /home/user/multi.txt")
        assert_success(result)
        assert stdout_text(result) == "\n".join(f"line {i}" for i in range(1, 6))

    async def test_head_shorthand(self, shell_with_commands):
        """``head -3`` expands to ``head -n 3``."""
        await self._write_multi(shell_with_commands)
        result = await shell_with_commands.execute("head -3 /home/user/multi.txt")
        assert_success(result)
        assert stdout_text(result) == "\n".join(f"line {i}" for i in range(1, 4))

    async def test_head_long_option(self, shell_with_commands):
        """``head --lines=7`` outputs the first 7 lines."""
        await self._write_multi(shell_with_commands)
        result = await shell_with_commands.execute("head --lines=7 /home/user/multi.txt")
        assert_success(result)
        assert stdout_text(result) == "\n".join(f"line {i}" for i in range(1, 8))

    # -- stdin fallback ----------------------------------------------------

    async def test_head_stdin_pipe(self, shell_with_commands):
        """``head`` with no file reads from stdin."""
        await self._write_multi(shell_with_commands)
        result = await shell_with_commands.execute("cat /home/user/multi.txt | head")
        assert_success(result)
        assert stdout_text(result) == "\n".join(f"line {i}" for i in range(1, 11))

    async def test_head_stdin_with_n(self, shell_with_commands):
        """``head -n 3`` reads from stdin with custom count."""
        shell_with_commands.filesystem.touch(
            "/home/user/data.txt", acting_user=shell_with_commands.user
        )
        shell_with_commands.filesystem.delta_layer[
            "/home/user/data.txt"
        ].content = "hello\nworld\nfoo\nbar\nbaz"
        result = await shell_with_commands.execute("cat /home/user/data.txt | head -n 3")
        assert_success(result)
        assert stdout_text(result) == "hello\nworld\nfoo"

    # -- edge cases --------------------------------------------------------

    async def test_head_file_shorter_than_n(self, shell_with_commands):
        """File with fewer lines than N outputs all lines."""
        shell_with_commands.filesystem.touch(
            "/home/user/short.txt", acting_user=shell_with_commands.user
        )
        shell_with_commands.filesystem.delta_layer[
            "/home/user/short.txt"
        ].content = "only\nthree\nlines"
        result = await shell_with_commands.execute("head -n 50 /home/user/short.txt")
        assert_success(result)
        assert stdout_text(result) == "only\nthree\nlines"

    async def test_head_n_zero(self, shell_with_commands):
        """``head -n 0`` outputs nothing."""
        await self._write_multi(shell_with_commands)
        result = await shell_with_commands.execute("head -n 0 /home/user/multi.txt")
        assert_success(result)
        assert stdout_text(result) == ""

    # -- errors ------------------------------------------------------------

    async def test_head_missing_file(self, shell_with_commands):
        """``head`` on a nonexistent file returns ERROR."""
        result = await shell_with_commands.execute("head /nonexistent")
        assert_error(result)
        assert CommandError.NOT_FOUND in stderr_text(result)

    async def test_head_is_directory(self, shell_with_commands):
        """``head`` on a directory returns ERROR with IS_A_DIRECTORY."""
        result = await shell_with_commands.execute("head /home")
        assert_error(result)
        assert CommandError.IS_A_DIRECTORY in stderr_text(result)

    async def test_head_invalid_n_value(self, shell_with_commands):
        """``head -n abc`` returns INVALID_ARGUMENT with GNU error message."""
        await self._write_multi(shell_with_commands)
        result = await shell_with_commands.execute("head -n abc /home/user/multi.txt")
        assert_invalid_args(result)
        assert "head: invalid number of lines: 'abc'" in stderr_text(result)

    # -- multi-file banners -------------------------------------------------

    async def test_head_two_files_shows_banners(self, shell_with_commands):
        """``head`` with two files outputs ``==> name <==`` banners."""
        await self._write_multi(shell_with_commands, "/home/user/a.txt")
        await self._write_multi(shell_with_commands, "/home/user/b.txt")
        result = await shell_with_commands.execute("head /home/user/a.txt /home/user/b.txt")
        assert_success(result)
        stdout = stdout_text(result)
        assert "==> /home/user/a.txt <==" in stdout
        assert "==> /home/user/b.txt <==" in stdout
        assert stdout.startswith("==> /home/user/a.txt <==")

    async def test_head_two_files_separator(self, shell_with_commands):
        """A blank line separates the second banner from the first file's content."""
        await self._write(shell_with_commands, "/home/user/a.txt", "first\n")
        await self._write(shell_with_commands, "/home/user/b.txt", "second\n")
        result = await shell_with_commands.execute("head /home/user/a.txt /home/user/b.txt")
        assert_success(result)
        stdout = stdout_text(result)
        assert "\n\n==> /home/user/b.txt <==" in stdout

    async def test_head_single_file_no_banner(self, shell_with_commands):
        """``head`` with one file does not show a banner."""
        await self._write(shell_with_commands, "/home/user/a.txt", "hello\n")
        result = await shell_with_commands.execute("head /home/user/a.txt")
        assert_success(result)
        assert stdout_text(result) == "hello"

    # -- stdin "-" argument -------------------------------------------------

    async def test_head_stdin_dash(self, shell_with_commands):
        """``head -`` reads from stdin."""
        result = await shell_with_commands.execute("echo hello | head -")
        assert_success(result)
        assert stdout_text(result) == "hello"

    async def test_head_stdin_dash_with_n(self, shell_with_commands):
        """``head -n 1 -`` reads one line from stdin."""
        await self._write(shell_with_commands, "/tmp/data.txt", "a\nb\nc\n")
        result = await shell_with_commands.execute("cat /tmp/data.txt | head -n 1 -")
        assert_success(result)
        assert stdout_text(result) == "a"

    async def test_head_stdin_dash_between_files(self, shell_with_commands):
        """``head file1 - file2`` interleaves file with stdin."""
        await self._write(shell_with_commands, "/home/user/a.txt", "from_a\n")
        await self._write(shell_with_commands, "/home/user/b.txt", "from_b\n")
        result = await shell_with_commands.execute(
            "echo from_stdin | head /home/user/a.txt - /home/user/b.txt"
        )
        assert_success(result)
        stdout = stdout_text(result)
        assert "==> /home/user/a.txt <==" in stdout
        assert "from_a" in stdout
        assert "==> - <==" in stdout
        assert "from_stdin" in stdout
        assert "==> /home/user/b.txt <==" in stdout
        assert "from_b" in stdout
