"""Integration tests for logical operator (&& and ||) execution via SNXShell."""

import pytest

from tests.helpers import assert_success, assert_error, stdout_text, stderr_text

pytestmark = pytest.mark.asyncio


class TestAndOperator:
    async def test_both_succeed(self, shell_with_commands):
        r = await shell_with_commands.execute("echo hello && echo world")
        assert_success(r)
        assert stdout_text(r) == "hello\nworld"

    async def test_first_fails_second_skipped(self, shell_with_commands):
        r = await shell_with_commands.execute("cat /nonexistent && echo world")
        assert_error(r)
        assert "world" not in stdout_text(r)
        assert len(r.stderr) > 0

    async def test_first_fails_both_skipped(self, shell_with_commands):
        r = await shell_with_commands.execute("cat /nonexistent && echo first && echo second")
        assert_error(r)
        assert stdout_text(r) == ""

    async def test_with_pipe(self, shell_with_commands):
        r = await shell_with_commands.execute("echo hello && echo world | cat")
        assert_success(r)
        assert "hello" in stdout_text(r)
        assert "world" in stdout_text(r)


class TestOrOperator:
    async def test_first_succeeds_second_skipped(self, shell_with_commands):
        r = await shell_with_commands.execute("echo hello || echo world")
        assert_success(r)
        assert stdout_text(r) == "hello"

    async def test_first_fails_second_runs(self, shell_with_commands):
        r = await shell_with_commands.execute("cat /nonexistent || echo fallback")
        assert_success(r)
        assert "fallback" in stdout_text(r)

    async def test_both_fail(self, shell_with_commands):
        r = await shell_with_commands.execute("cat /nonexistent1 || cat /nonexistent2")
        assert_error(r)

    async def test_with_pipe(self, shell_with_commands):
        r = await shell_with_commands.execute("cat /nonexistent || echo fallback | cat")
        assert_success(r)
        assert "fallback" in stdout_text(r)


class TestMixedChains:
    async def test_and_or_chain(self, shell_with_commands):
        r = await shell_with_commands.execute("cat /nonexistent && echo first || echo fallback")
        assert_success(r)
        assert "fallback" in stdout_text(r)

    async def test_or_and_chain(self, shell_with_commands):
        r = await shell_with_commands.execute("echo hello || echo skipped && echo final")
        assert_success(r)
        lines = stdout_text(r).strip().split("\n")
        assert "hello" in lines
        assert "final" in lines
        assert "skipped" not in lines

    async def test_triple_chain(self, shell_with_commands):
        r = await shell_with_commands.execute("echo a && echo b || echo c")
        assert_success(r)
        assert stdout_text(r) == "a\nb"


class TestLogicalWithTestCommand:
    async def test_bracket_and_echo(self, shell_with_commands):
        r = await shell_with_commands.execute("touch /home/user/notes.txt")
        assert_success(r)
        r2 = await shell_with_commands.execute("[ -f /home/user/notes.txt ] && echo YES")
        assert_success(r2)
        assert "YES" in stdout_text(r2)

    async def test_bracket_fail_or_echo(self, shell_with_commands):
        r = await shell_with_commands.execute("[ -f /home/user/missing.txt ] && echo YES || echo NO")
        assert_success(r)
        assert "NO" in stdout_text(r)
        assert "YES" not in stdout_text(r)
