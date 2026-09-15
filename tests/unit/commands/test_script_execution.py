"""Tests for VFS script execution (./script.sh) and the sh/bash commands."""

import pytest

from tests.helpers import assert_error
from tests.helpers import assert_invalid_args
from tests.helpers import assert_success
from tests.helpers import stderr_text
from tests.helpers import stdout_text


pytestmark = pytest.mark.asyncio


SCRIPT = """\
#!/bin/sh
# this is a comment
echo hello

echo world

# another comment
echo foo
"""


class TestScriptExecution:
    """Shell-level integration tests for script execution."""

    async def _write_script(self, shell, content=SCRIPT, path="/home/user/script.sh"):
        shell.filesystem.touch(path, execution=shell.execution_context)
        shell.filesystem.delta_layer[path].content = content
        shell.filesystem.chmod(path, 0o755, execution=shell.execution_context)

    # -- direct execution --------------------------------------------------

    async def test_direct_script_execution(self, shell_with_commands):
        """``./script.sh`` executes lines sequentially."""
        await self._write_script(shell_with_commands)
        result = await shell_with_commands.execute("./script.sh")
        assert_success(result)
        assert stdout_text(result) == "hello\nworld\nfoo"

    async def test_script_skips_comments_and_empty_lines(self, shell_with_commands):
        """Comments, shebang, and blank lines are ignored."""
        content = """\
#!/bin/bash
# comment one

echo first
# comment two


echo second
"""
        await self._write_script(shell_with_commands, content=content)
        result = await shell_with_commands.execute("./script.sh")
        assert_success(result)
        assert stdout_text(result) == "first\nsecond"

    async def test_script_with_absolute_path(self, shell_with_commands):
        """Absolute path to script also resolves and executes."""
        await self._write_script(shell_with_commands)
        result = await shell_with_commands.execute("/home/user/script.sh")
        assert_success(result)
        assert stdout_text(result) == "hello\nworld\nfoo"

    async def test_missing_script_returns_error(self, shell_with_commands):
        """``./nonexistent.sh`` returns an error message."""
        result = await shell_with_commands.execute("./nonexistent.sh")
        assert_error(result)
        assert "not found" in stderr_text(result)

    # -- piped execution ---------------------------------------------------

    async def test_script_piped_to_grep(self, shell_with_commands):
        """``./script.sh | grep <pattern>`` filters output."""
        await self._write_script(shell_with_commands)
        result = await shell_with_commands.execute("./script.sh | grep wo")
        assert_success(result)
        assert stdout_text(result) == "world"

    # -- redirected execution ----------------------------------------------

    async def test_script_redirected_to_file(self, shell_with_commands):
        """``./script.sh > output.txt`` writes to file."""
        await self._write_script(shell_with_commands)
        result = await shell_with_commands.execute("./script.sh > /home/user/output.txt")
        assert_success(result)

        read_result = shell_with_commands.filesystem.read(
            "/home/user/output.txt",
            execution=shell_with_commands.execution_context,
        )
        assert read_result.exit_code == 0
        assert read_result.node.content == "helloworldfoo"

    # -- sh command --------------------------------------------------------

    async def test_sh_command_reads_and_executes_script(self, shell_with_commands):
        """``sh ./script.sh`` executes the script."""
        await self._write_script(shell_with_commands)
        result = await shell_with_commands.execute("sh ./script.sh")
        assert_success(result)
        assert stdout_text(result) == "hello\nworld\nfoo"

    async def test_sh_command_with_relative_path(self, shell_with_commands):
        """``sh script.sh`` resolves relative to current directory."""
        await self._write_script(shell_with_commands)
        result = await shell_with_commands.execute("sh script.sh")
        assert_success(result)
        assert stdout_text(result) == "hello\nworld\nfoo"

    async def test_sh_command_missing_file(self, shell_with_commands):
        """``sh nonexistent.sh`` returns an error."""
        result = await shell_with_commands.execute("sh nonexistent.sh")
        assert_error(result)
        assert "not found" in stderr_text(result)

    async def test_sh_command_no_args(self, shell_with_commands):
        """``sh`` with no arguments returns an error."""
        result = await shell_with_commands.execute("sh")
        assert_invalid_args(result)
        assert "missing file operand" in stderr_text(result)

    # -- bash alias --------------------------------------------------------

    async def test_bash_alias_executes_script(self, shell_with_commands):
        """``bash ./script.sh`` works identically to ``sh``."""
        await self._write_script(shell_with_commands)
        result = await shell_with_commands.execute("bash ./script.sh")
        assert_success(result)
        assert stdout_text(result) == "hello\nworld\nfoo"
