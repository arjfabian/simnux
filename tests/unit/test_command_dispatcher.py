"""Tests for the CommandDispatcher dispatch layer.

Validates that command name resolution and delegation to registered
command instances works correctly, including error propagation and
registry isolation.
"""

import pytest

from simnux.core.commands.dispatcher import CommandDispatcher
from simnux.core.commands.models import CommandContext
from simnux.core.commands.registry import CommandRegistry
from simnux.core.commands.runtime import SNXCommand
from simnux.core.commands.streams import AsyncStreamReader
from simnux.core.commands.streams import AsyncStreamWriter
from simnux.core.filesystem.models import PermissionPresets
from simnux.core.filesystem.models import SNXNode
from simnux.core.filesystem.vfs import SNXFileSystem
from simnux.core.runtime.models import ExitCode
from simnux.core.scenarios.models import SNXScenario
from simnux.core.sessions.runtime import SNXSession


pytestmark = pytest.mark.asyncio


class _SimpleCommand(SNXCommand):
    name = "simple"

    async def execute(
        self,
        ctx: CommandContext,
        stdin: AsyncStreamReader,
        stdout: AsyncStreamWriter,
        stderr: AsyncStreamWriter,
    ) -> ExitCode:
        await stdout.write(f"executed with {self.args}")
        return ExitCode.SUCCESS


class _FailingCommand(SNXCommand):
    name = "fails"

    async def execute(
        self,
        ctx: CommandContext,
        stdin: AsyncStreamReader,
        stdout: AsyncStreamWriter,
        stderr: AsyncStreamWriter,
    ) -> ExitCode:
        raise RuntimeError("something went wrong")


def make_registry(*commands):
    registry = CommandRegistry()

    for command_cls in commands:
        registry.register(command_cls(context=None))

    return registry


@pytest.fixture
def ctx():
    scenario = SNXScenario(
        name="test",
        difficulty="easy",
        username="user",
        hostname="host",
        starting_dir="/",
        filesystem={
            "/": SNXNode(
                path="/",
                content="",
                is_directory=True,
                permissions=PermissionPresets.DIRECTORY_DEFAULT,
            ),
        },
    )
    session = SNXSession(session_id="test", scenario=scenario, current_directory="/")
    filesystem = SNXFileSystem(base_layer={})
    return CommandContext(session=session, filesystem=filesystem)


@pytest.fixture
def registry():
    return make_registry(_SimpleCommand)


@pytest.fixture
def dispatcher(registry):
    return CommandDispatcher(registry=registry)


class TestCommandDispatcher:
    """Happy-path dispatch scenarios.

    Covers successful command resolution and empty-arg boundary cases.
    Uses the ``dispatcher`` fixture with a single ``_SimpleCommand``
    registered under the name ``"simple"``.
    """

    async def test_successful_dispatch(self, dispatcher, ctx):
        """Dispatch to a registered command returns its result with SUCCESS exit code."""
        result = await dispatcher.dispatch("simple", ["a", "b"], ctx)

        assert result.stdout == ["executed with ['a', 'b']"]
        assert result.stderr == []
        assert result.exit_code == ExitCode.SUCCESS

    async def test_dispatch_empty_args(self, dispatcher, ctx):
        """Dispatch with an empty argument list should still succeed (boundary case)."""
        result = await dispatcher.dispatch("simple", [], ctx)

        assert result.stdout == ["executed with []"]
        assert result.stderr == []
        assert result.exit_code == ExitCode.SUCCESS


class TestCommandDispatcherErrors:
    """Error-handling dispatch scenarios.

    Verifies that missing commands return an error result and that
    exceptions thrown by command execution propagate correctly.
    """

    async def test_missing_command_returns_error(self, dispatcher, ctx):
        """Dispatching an unregistered command returns an error result."""
        result = await dispatcher.dispatch("nonexistent", [], ctx)
        assert result.exit_code == ExitCode.ERROR
        assert "not found" in "\n".join(result.stderr)

    async def test_exception_propagation(self, ctx):
        """Exceptions raised inside command ``execute()`` propagate to the caller."""
        dispatcher = CommandDispatcher(
            registry=make_registry(
                _SimpleCommand,
                _FailingCommand,
            )
        )

        with pytest.raises(RuntimeError, match="something went wrong"):
            await dispatcher.dispatch("fails", [], ctx)


class TestCommandDispatcherIsolation:
    """Ensures each ``CommandDispatcher`` instance operates on its own registry.

    Two dispatchers backed by different registries must not share state;
    a command available in one must not be visible in the other.
    """

    async def test_dispatcher_different_registries_isolated(self, ctx):
        """Dispatchers with separate registries do not share command availability."""
        dispatcher1 = CommandDispatcher(registry=make_registry(_SimpleCommand))

        result = await dispatcher1.dispatch("simple", [], ctx)

        assert result.stdout == ["executed with []"]
        assert result.exit_code == ExitCode.SUCCESS

        dispatcher2 = CommandDispatcher(registry=make_registry())

        result = await dispatcher2.dispatch("simple", [], ctx)
        assert result.exit_code == ExitCode.ERROR
