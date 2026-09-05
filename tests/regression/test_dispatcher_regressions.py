"""Regression tests for CommandDispatcher assumptions.

Validates that the dispatcher correctly errors on unregistered commands
and succeeds after registration (foundational invariants).
"""

import logging

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
from simnux.core.shell.runtime import SNXShell
from simnux.security.groups.models import SNXGroup
from simnux.security.users.models import SNXUser


pytestmark = pytest.mark.asyncio


@pytest.fixture
def ctx():
    scenario = SNXScenario(
        name="test",
        difficulty="easy",
        hostname="host",
        users={
            "root": SNXUser(0, "root"),
            "user": SNXUser(1001, "user"),
        },
        groups={
            "root": SNXGroup(0, "root"),
            "user": SNXGroup(1001, "user"),
        },
        starting_dir="/",
        filesystem={
            "/": SNXNode(
                path="/",
                owner=SNXUser(0, "root"),
                group=SNXGroup(0, "root"),
                content="",
                is_directory=True,
                permissions=PermissionPresets.DIRECTORY_DEFAULT,
            ),
        },
    )
    filesystem = SNXFileSystem(base_layer={})
    shell = SNXShell(
        scenario=scenario,
        user=scenario.users["user"],
        current_directory="/",
        filesystem=filesystem,
        registry=CommandRegistry(),
        logger=logging.getLogger("test_dispatcher"),
        identifier="test",
    )
    return CommandContext(shell=shell, filesystem=filesystem)


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
