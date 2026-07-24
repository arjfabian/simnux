"""Regression tests for CommandDispatcher assumptions.

Validates that the dispatcher correctly errors on unregistered commands
and succeeds after registration (foundational invariants).
"""


import pytest

from simnux.commands.dispatcher import CommandDispatcher
from simnux.commands.models import CommandContext
from simnux.commands.registry import CommandRegistry
from simnux.commands.runtime import SNXCommand
from simnux.commands.streams import AsyncStreamReader
from simnux.commands.streams import AsyncStreamWriter
from simnux.filesystem.models import SNXNode
from simnux.filesystem.models import PermissionPresets
from simnux.filesystem.vfs import SNXFileSystem
from simnux.runtime.models import ExitCode
from simnux.scenarios.models import SNXScenario
from simnux.sessions.runtime import SNXSession


pytestmark = pytest.mark.asyncio


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


class TestRegressionDispatcherAssumptions:
    """Fundamental dispatcher invariants: fail fast on unknown, work on registered."""

    async def test_dispatch_to_unregistered_command_returns_error(self, ctx):
        """Dispatching an unregistered command returns an error result."""
        registry = CommandRegistry()
        dispatcher = CommandDispatcher(registry=registry)
        result = await dispatcher.dispatch("unknown", [], ctx)
        assert result.exit_code == ExitCode.ERROR
        assert "not found" in "\n".join(result.stderr)

    async def test_dispatch_after_registration_succeeds(self, ctx):
        """Dispatching a registered command returns its result."""
        registry = CommandRegistry()

        class TestCmd(SNXCommand):
            name = "testcmd"

            async def execute(
                self,
                ctx: CommandContext,
                stdin: AsyncStreamReader,
                stdout: AsyncStreamWriter,
                stderr: AsyncStreamWriter,
            ) -> ExitCode:
                await stdout.write("ok")
                return ExitCode.SUCCESS

        registry.register(TestCmd(context=None))
        dispatcher = CommandDispatcher(registry=registry)
        result = await dispatcher.dispatch("testcmd", [], ctx)
        assert result.stdout == ["ok"]
        assert result.stderr == []
        assert result.exit_code == ExitCode.SUCCESS
