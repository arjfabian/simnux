"""Tests for shell pipeline execution (``cmd1 | cmd2``).

Exercises the full path: parser → dispatcher → pipeline orchestration.
Uses the ``shell_with_commands`` fixture for real command execution.
"""

import pytest

from tests.helpers import assert_success
from tests.helpers import stdout_text


pytestmark = pytest.mark.asyncio


class TestPipeline:
    """End-to-end pipeline execution through the shell."""

    async def test_ls_grep_pipe(self, shell_with_commands):
        """``ls | grep pattern`` filters listing output."""
        shell = shell_with_commands
        await shell.execute("touch /home/user/notes.txt")

        result = await shell.execute("ls /home/user | grep notes")
        assert_success(result)
        assert "notes" in stdout_text(result)

    async def test_cat_grep_pipe(self, shell_with_commands):
        """``cat file | grep pattern`` filters file content."""
        shell = shell_with_commands
        result = await shell.execute("cat /home/user/notes.txt | grep hello")
        assert_success(result)
        assert stdout_text(result) == "hello world"

    async def test_cat_grep_no_match(self, shell_with_commands):
        """No match in pipeline returns empty stdout."""
        shell = shell_with_commands
        result = await shell.execute("cat /home/user/notes.txt | grep nonexistent")
        assert result.exit_code == 1
        assert stdout_text(result) == ""

    async def test_pipe_with_redirect(self, shell_with_commands):
        """Pipeline with redirect on the last command writes to file."""
        shell = shell_with_commands
        result = await shell.execute("cat /home/user/notes.txt | grep hello > /home/user/out.txt")
        assert_success(result)
        assert stdout_text(result) == ""

        verify = await shell.execute("cat /home/user/out.txt")
        assert stdout_text(verify) == "hello world"

    async def test_three_stage_pipe(self, shell_with_commands):
        """Three-stage pipeline: cat, grep, second grep."""
        shell = shell_with_commands
        result = await shell.execute("cat /home/user/notes.txt | grep hello | grep world")
        assert_success(result)
        output = stdout_text(result)
        assert "hello world" in output

    async def test_first_command_fails_pipeline(self, shell_with_commands):
        """When the first command fails, the pipeline reports the error."""
        shell = shell_with_commands
        result = await shell.execute("cat /nonexistent | grep anything")
        assert "not found" in "\n".join(result.stderr)

    async def test_second_command_fails_in_pipe(self, shell_with_commands):
        """When a later command fails, stderr from that command is captured."""
        shell = shell_with_commands
        result = await shell.execute("echo foo | cat /nonexistent")
        assert "not found" in "\n".join(result.stderr)
