"""Tests for variable expansion and assignment in script loops."""

import asyncio
from typing import ClassVar
from unittest.mock import MagicMock

import pytest

from simnux.boot.config import LimitsConfig
from simnux.boot.config import ScriptLimits
from simnux.core.commands.models import CommandContext
from simnux.core.commands.registry import CommandRegistry
from simnux.core.commands.standard.condition import Command as TestCmd
from simnux.core.commands.streams import QueueStreamWriter
from simnux.core.runtime.models import ExitCode
from simnux.core.scripting.runner import ScriptRunner
from simnux.security.execution.models import ExecutionContext
from simnux.security.users.models import SNXUser


_ROOT_USER = SNXUser(0, "root")


class _EchoCommand:
    """Echo command that writes args (space-separated) to stdout."""

    name = "echo"
    aliases: ClassVar[list[str]] = []
    args: ClassVar[list[str]] = []
    _invoked_name = "echo"
    parameters = None
    parsed_args = None
    action_type = 0

    async def execute(self, ctx, stdin, stdout, stderr):
        await stdout.write(" ".join(self.args))
        return ExitCode.SUCCESS


class _TrueCommand:
    """Stub ``true`` — always succeeds."""

    name = "true"
    aliases: ClassVar[list[str]] = []
    args: ClassVar[list[str]] = []
    _invoked_name = "true"
    parameters = None
    parsed_args = None
    action_type = 0

    async def execute(self, ctx, stdin, stdout, stderr):
        return ExitCode.SUCCESS


def _make_runner(
    limits: LimitsConfig | None = None,
) -> tuple[ScriptRunner, CommandContext]:
    limits = limits or LimitsConfig()
    registry = CommandRegistry()
    runner = ScriptRunner(registry, limits=limits)
    registry.register(_EchoCommand())
    registry.register(_TrueCommand())
    registry.register(TestCmd(context=None))

    session = MagicMock()
    session.execution_context = ExecutionContext.for_user(_ROOT_USER)
    session.session_id = "test"
    session.current_directory = "/home/user"
    session.home_directory = "/home/user"
    session.environment = {}

    filesystem = MagicMock()
    filesystem.resolve_path.return_value = "/home/user"

    ctx = CommandContext(
        shell=session,
        filesystem=filesystem,
        execution_context=session.execution_context,
    )
    return runner, ctx


async def _run_script(runner, ctx, script) -> tuple[ExitCode, list[str]]:
    stdin = MagicMock()
    stdout = QueueStreamWriter(asyncio.Queue())
    stderr = QueueStreamWriter(asyncio.Queue())

    result = await runner.execute(script, ctx, stdin, stdout, stderr)

    stdout_lines = []
    while not stdout._queue.empty():
        stdout_lines.append(stdout._queue.get_nowait())

    stderr_lines = []
    while not stderr._queue.empty():
        stderr_lines.append(stderr._queue.get_nowait())

    return result.exit_code, stdout_lines, stderr_lines


# ── for-loop variable expansion ─────────────────────────────────────────


class TestForLoopVariableExpansion:
    """Variable substitution inside for-loop bodies."""

    pytestmark = pytest.mark.asyncio

    async def test_for_expands_loop_var_in_echo(self):
        """for i in a b c; echo $i — outputs a, b, c."""
        runner, ctx = _make_runner()
        script = "for i in a b c\n  echo $i\ndone"
        exit_code, stdout, _ = await _run_script(runner, ctx, script)

        assert exit_code == ExitCode.SUCCESS
        assert stdout == ["a", "b", "c"]

    async def test_for_expands_braced_var(self):
        """for item in alpha beta; echo ${item} — outputs alpha, beta."""
        runner, ctx = _make_runner()
        script = "for item in alpha beta\n  echo ${item}\ndone"
        exit_code, stdout, _ = await _run_script(runner, ctx, script)

        assert exit_code == ExitCode.SUCCESS
        assert stdout == ["alpha", "beta"]

    async def test_for_expands_multiple_vars_per_line(self):
        """for i in x y; echo $i-$i — outputs x-x, y-y."""
        runner, ctx = _make_runner()
        script = "for i in x y\n  echo $i-$i\ndone"
        exit_code, stdout, _ = await _run_script(runner, ctx, script)

        assert exit_code == ExitCode.SUCCESS
        assert stdout == ["x-x", "y-y"]

    async def test_for_unset_var_expands_empty(self):
        """Unset variables expand to empty string."""
        runner, ctx = _make_runner()
        script = "for i in a b\n  echo $i$unset\ndone"
        exit_code, stdout, _ = await _run_script(runner, ctx, script)

        assert exit_code == ExitCode.SUCCESS
        assert stdout == ["a", "b"]


# ── while-loop variable expansion & assignment ──────────────────────────


class TestWhileLoopVariableExpansion:
    """Variable expansion and assignment inside while-loop bodies."""

    pytestmark = pytest.mark.asyncio

    async def test_while_with_counter(self):
        """while loop with i=1, i=$((i+1)), $i — runs to completion."""
        runner, ctx = _make_runner(LimitsConfig(script=ScriptLimits(max_loop_iterations=100)))
        # This script should run 3 iterations and exit cleanly
        script = "i=1\nwhile [ $i -le 3 ]\n  echo $i\n  i=$((i+1))\ndone"
        exit_code, stdout, stderr = await _run_script(runner, ctx, script)

        assert exit_code == ExitCode.SUCCESS, f"stderr: {stderr}"
        assert stdout == ["1", "2", "3"]

    async def test_while_assignment_only_no_crash(self):
        """while loop with only assignments — no crash, no internal error."""
        runner, ctx = _make_runner(LimitsConfig(script=ScriptLimits(max_loop_iterations=10)))
        script = "x=hello\nwhile [ $x = hello ]\n  x=goodbye\ndone"
        exit_code, _, stderr = await _run_script(runner, ctx, script)

        assert exit_code == ExitCode.SUCCESS, f"stderr: {stderr}"
        # x started as "hello", condition true once, set to "goodbye", then false
        assert ctx.shell.environment.get("x") == "goodbye"

    async def test_while_increment_reaches_zero(self):
        """while loop counting down: i=3; while [ $i -gt 0 ]; i=$((i-1))."""
        runner, ctx = _make_runner(LimitsConfig(script=ScriptLimits(max_loop_iterations=100)))
        script = "i=3\nwhile [ $i -gt 0 ]\n  echo $i\n  i=$((i-1))\ndone"
        exit_code, stdout, stderr = await _run_script(runner, ctx, script)

        assert exit_code == ExitCode.SUCCESS, f"stderr: {stderr}"
        assert stdout == ["3", "2", "1"]

    async def test_while_arithmetic_no_crash(self):
        """Arithmetic in condition doesn't produce internal error."""
        runner, ctx = _make_runner(LimitsConfig(script=ScriptLimits(max_loop_iterations=100)))
        # Condition uses arithmetic directly
        script = "n=1\nwhile [ $((n)) -le 3 ]\n  echo tick\n  n=$((n+1))\ndone"
        exit_code, stdout, stderr = await _run_script(runner, ctx, script)

        assert exit_code == ExitCode.SUCCESS, f"stderr: {stderr}"
        assert stdout == ["tick", "tick", "tick"]


# ── Assignment outside loops ────────────────────────────────────────────


class TestStandaloneAssignment:
    """Variable assignment lines that are not inside loops."""

    pytestmark = pytest.mark.asyncio

    async def test_simple_assignment(self):
        """VAR=VALUE sets the variable in the environment."""
        runner, ctx = _make_runner()
        script = "foo=bar\n"
        exit_code, _, _ = await _run_script(runner, ctx, script)

        assert exit_code == ExitCode.SUCCESS
        assert ctx.shell.environment["foo"] == "bar"

    async def test_assignment_before_echo(self):
        """Assignment followed by echo using the variable."""
        runner, ctx = _make_runner()
        script = "greeting=hello\necho $greeting"
        exit_code, stdout, _ = await _run_script(runner, ctx, script)

        assert exit_code == ExitCode.SUCCESS
        assert stdout == ["hello"]


# ── Exception handling ──────────────────────────────────────────────────


class TestScriptErrorHandling:
    """Script errors produce clean messages, not Internal runtime error."""

    pytestmark = pytest.mark.asyncio

    async def test_unknown_command_does_not_crash(self):
        """Unknown command in script body produces 'command not found'."""
        runner, ctx = _make_runner()
        script = "nosuchcmd arg1 arg2"
        exit_code, _, stderr = await _run_script(runner, ctx, script)

        assert exit_code == ExitCode.ERROR
        assert any("command not found" in line for line in stderr)
        assert not any("Internal" in line for line in stderr)

    async def test_bad_syntax_does_not_crash(self):
        """Malformed redirect produces clean error, not Internal error."""
        runner, ctx = _make_runner()
        script = "echo >"
        exit_code, _, stderr = await _run_script(runner, ctx, script)

        assert exit_code != ExitCode.SUCCESS
        assert not any("Internal" in line for line in stderr)


# ── _expand_vars unit tests ────────────────────────────────────────────


class TestExpandVars:
    """Direct tests for the _expand_vars helper."""

    def test_simple_var(self):
        runner, _ = _make_runner()
        assert runner._expand_vars("$x", {"x": "hello"}) == "hello"

    def test_braced_var(self):
        runner, _ = _make_runner()
        assert runner._expand_vars("${name}", {"name": "world"}) == "world"

    def test_unset_var_empty(self):
        runner, _ = _make_runner()
        assert runner._expand_vars("$missing", {}) == ""

    def test_multiple_vars(self):
        runner, _ = _make_runner()
        env = {"a": "1", "b": "2"}
        assert runner._expand_vars("$a-$b", env) == "1-2"

    def test_arithmetic_expansion(self):
        runner, _ = _make_runner()
        env = {"i": "5"}
        assert runner._expand_vars("$((i+3))", env) == "8"

    def test_nested_arithmetic_with_vars(self):
        runner, _ = _make_runner()
        env = {"a": "10", "b": "3"}
        assert runner._expand_vars("$((a*b))", env) == "30"

    def test_literal_dollar_not_variable(self):
        """A literal $ not followed by a word char is preserved."""
        runner, _ = _make_runner()
        assert runner._expand_vars("cost: $5", {}) == "cost: $5"


class TestEvalArithmetic:
    """Direct tests for the _eval_arithmetic helper."""

    def test_addition(self):
        from simnux.core.scripting.runner import ScriptRunner

        assert ScriptRunner._eval_arithmetic("2+3", {}) == 5

    def test_subtraction(self):
        from simnux.core.scripting.runner import ScriptRunner

        assert ScriptRunner._eval_arithmetic("10-7", {}) == 3

    def test_with_var(self):
        from simnux.core.scripting.runner import ScriptRunner

        assert ScriptRunner._eval_arithmetic("x+1", {"x": "4"}) == 5

    def test_division_by_zero(self):
        from simnux.core.scripting.runner import ScriptRunner

        assert ScriptRunner._eval_arithmetic("1/0", {}) == 0

    def test_invalid_expr_returns_zero(self):
        from simnux.core.scripting.runner import ScriptRunner

        assert ScriptRunner._eval_arithmetic("abc", {}) == 0


# ── Nested for-loop body collection ──────────────────────────────────


class TestNestedForLoop:
    """Nested for loops with inline ``do`` on the header line."""

    pytestmark = pytest.mark.asyncio

    async def test_nested_for_inner_and_outer_execute(self):
        """Inner for loop runs fully, outer for loop runs fully."""
        runner, ctx = _make_runner()
        # Nested: outer iterates a b, inner iterates x y
        # Total echo calls: 2 outer × 2 inner = 4
        script = "for i in a b; do\n  for j in x y; do\n    echo $i$j\n  done\ndone\n"
        exit_code, stdout, _ = await _run_script(runner, ctx, script)
        assert exit_code == ExitCode.SUCCESS
        assert stdout == ["ax", "ay", "bx", "by"]

    async def test_nested_for_no_done_leak(self):
        """No 'done: command not found' error at the end of a nested for."""
        runner, ctx = _make_runner()
        script = "for i in a b; do\n  for j in x y; do\n    echo $j\n  done\ndone\n"
        exit_code, _, stderr = await _run_script(runner, ctx, script)
        assert exit_code == ExitCode.SUCCESS
        assert not any("command not found" in e for e in stderr)

    async def test_nested_for_with_empty_body(self):
        """Nested for with no commands in inner body."""
        runner, ctx = _make_runner()
        script = "for i in a b; do\n  for j in x y; do\n  done\ndone\n"
        exit_code, _, stderr = await _run_script(runner, ctx, script)
        assert exit_code == ExitCode.SUCCESS
        assert not any("command not found" in e for e in stderr)


# ── Shell keyword skip ───────────────────────────────────────────────


class TestKeywordsSkip:
    """Stray shell keywords are silently skipped, not dispatched as commands."""

    pytestmark = pytest.mark.asyncio

    async def test_done_alone_is_skipped(self):
        """A bare 'done' at the top level should not produce command not found."""
        runner, ctx = _make_runner()
        exit_code, _, stderr = await _run_script(runner, ctx, "done\n")
        assert exit_code == ExitCode.SUCCESS
        assert not any("command not found" in e for e in stderr)

    async def test_fi_alone_is_skipped(self):
        """A bare 'fi' at the top level should not produce command not found."""
        runner, ctx = _make_runner()
        exit_code, _, stderr = await _run_script(runner, ctx, "fi\n")
        assert exit_code == ExitCode.SUCCESS
        assert not any("command not found" in e for e in stderr)

    async def test_then_alone_is_skipped(self):
        """A bare 'then' should not produce command not found."""
        runner, ctx = _make_runner()
        exit_code, _, stderr = await _run_script(runner, ctx, "then\n")
        assert exit_code == ExitCode.SUCCESS
        assert not any("command not found" in e for e in stderr)

    async def test_do_alone_is_skipped(self):
        """A bare 'do' should not produce command not found."""
        runner, ctx = _make_runner()
        exit_code, _, stderr = await _run_script(runner, ctx, "do\n")
        assert exit_code == ExitCode.SUCCESS
        assert not any("command not found" in e for e in stderr)

    async def test_in_alone_is_skipped(self):
        """A bare 'in' should not produce command not found."""
        runner, ctx = _make_runner()
        exit_code, _, stderr = await _run_script(runner, ctx, "in\n")
        assert exit_code == ExitCode.SUCCESS
        assert not any("command not found" in e for e in stderr)
