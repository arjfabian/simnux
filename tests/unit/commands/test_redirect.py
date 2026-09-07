"""Tests for shell-level stdout redirection (``>``, ``>>``).

Exercises the full path: parser → dispatcher → FileStreamWriter → VFS.
Uses ``shell_with_commands`` fixture (all commands loaded) to run real
commands and verify file content via ``cat`` or direct VFS reads.
"""

import pytest

from tests.helpers import assert_success
from tests.helpers import stderr_text
from tests.helpers import stdout_text


pytestmark = pytest.mark.asyncio


class TestStdoutRedirect:
    """``>`` truncate redirect: echo ``>`` file, then verify content."""

    async def test_redirect_stdout_to_new_file(self, shell_with_commands):
        """echo hello > newfile creates file with content, stdout is empty."""
        shell = shell_with_commands
        result = await shell.execute("echo hello > /home/user/out.txt")
        assert_success(result)
        assert stdout_text(result) == "", "stdout should be empty when redirected"

        # Verify file content via cat
        verify = await shell.execute("cat /home/user/out.txt")
        assert_success(verify)
        assert stdout_text(verify) == "hello"

    async def test_redirect_stdout_overwrites_existing(self, shell_with_commands):
        """Repeated ``>`` overwrites previous content."""
        shell = shell_with_commands
        await shell.execute("echo first > /home/user/out.txt")
        await shell.execute("echo second > /home/user/out.txt")

        verify = await shell.execute("cat /home/user/out.txt")
        assert stdout_text(verify) == "second"

    async def test_redirect_stdout_no_command_output(self, shell_with_commands):
        """Command with no stdout output produces empty file on redirect."""
        shell = shell_with_commands
        result = await shell.execute("touch /home/user/empty.txt")
        assert_success(result)

        result = await shell.execute("cat /home/user/empty.txt > /home/user/copy.txt")
        assert_success(result)
        assert stdout_text(result) == ""

    async def test_redirect_multiline_output(self, shell_with_commands):
        """Multi-line command output is fully written to the file."""
        shell = shell_with_commands
        await shell.execute("echo line1 > /home/user/multi.txt")
        await shell.execute("echo line2 >> /home/user/multi.txt")
        await shell.execute("echo line3 >> /home/user/multi.txt")

        verify = await shell.execute("cat /home/user/multi.txt")
        assert stdout_text(verify) == "line1line2line3"

    async def test_redirect_stderr_still_captured_in_result(self, shell_with_commands):
        """Stderr is still returned in CommandResult when stdout is redirected."""
        shell = shell_with_commands
        result = await shell.execute("cat /nonexistent > /dev/null")
        assert "not found" in stderr_text(result)


class TestStdoutAppendRedirect:
    """``>>`` append redirect: echo ``>>`` file accumulates content."""

    async def test_append_to_new_file(self, shell_with_commands):
        """Appending to a non-existent file creates it first."""
        shell = shell_with_commands
        result = await shell.execute("echo hello >> /home/user/appended.txt")
        assert_success(result)
        assert stdout_text(result) == ""

        verify = await shell.execute("cat /home/user/appended.txt")
        assert stdout_text(verify) == "hello"

    async def test_append_to_existing_file(self, shell_with_commands):
        """Appending to an existing file adds content."""
        shell = shell_with_commands
        await shell.execute("echo first > /home/user/log.txt")
        await shell.execute("echo second >> /home/user/log.txt")
        await shell.execute("echo third >> /home/user/log.txt")

        verify = await shell.execute("cat /home/user/log.txt")
        assert stdout_text(verify) == "firstsecondthird"

    async def test_redirect_and_append_sequence(self, shell_with_commands):
        """Mix of ``>`` and ``>>`` produces expected content."""
        shell = shell_with_commands
        await shell.execute("echo alpha > /home/user/mix.txt")
        await shell.execute("echo beta >> /home/user/mix.txt")
        await shell.execute("echo gamma >> /home/user/mix.txt")
        await shell.execute("echo delta > /home/user/mix.txt")  # overwrite

        verify = await shell.execute("cat /home/user/mix.txt")
        assert stdout_text(verify) == "delta"

    async def test_redirect_relative_path(self, shell_with_commands):
        """Relative redirect target is resolved against cwd."""
        shell = shell_with_commands
        await shell.execute("echo hello > relative.txt")
        verify = await shell.execute("cat /home/user/relative.txt")
        assert stdout_text(verify) == "hello"

    async def test_redirect_tilde_path(self, shell_with_commands):
        """``~`` in redirect target is expanded to home directory."""
        shell = shell_with_commands
        await shell.execute("echo hello > ~/tilde.txt")
        verify = await shell.execute("cat /home/user/tilde.txt")
        assert stdout_text(verify) == "hello"

    async def test_redirect_after_cd(self, shell_with_commands):
        """Redirect target is resolved after ``cd`` changes cwd."""
        shell = shell_with_commands
        await shell.execute("mkdir workdir")
        await shell.execute("cd workdir")
        await shell.execute("echo hello > from_workdir.txt")
        verify = await shell.execute("cat /home/user/workdir/from_workdir.txt")
        assert stdout_text(verify) == "hello"
