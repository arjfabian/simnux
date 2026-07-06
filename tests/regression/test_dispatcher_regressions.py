"""Regression tests for CommandDispatcher assumptions.

Validates that the dispatcher correctly raises on unregistered commands
and succeeds after registration (foundational invariants).
"""

import asyncio

import pytest

from simnux.commands.dispatcher import CommandDispatcher
from simnux.commands.models import CommandContext
from simnux.commands.registry import CommandRegistry
from simnux.commands.runtime import SNXCommand
from simnux.commands.streams import AsyncStreamReader
from simnux.commands.streams import AsyncStreamWriter
from simnux.runtime.models import ExitCode


pytestmark = pytest.mark.asyncio


@pytest.fixture
def ctx():
    return object()


class TestRegressionDispatcherAssumptions:
    """Fundamental dispatcher invariants: fail fast on unknown, work on registered."""

    async def test_dispatch_to_unregistered_command_raises(self, ctx):
        """Dispatching an unregistered command raises ``ValueError``."""
        registry = CommandRegistry()
        dispatcher = CommandDispatcher(registry=registry)
        with pytest.raises(ValueError, match="not registered"):
            await dispatcher.dispatch("unknown", [], ctx)

    async def test_dispatch_after_registration_succeeds(self, ctx):
        """Dispatching a registered command returns its result."""
        registry = CommandRegistry()
        from simnux.commands.runtime import SNXCommand

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
