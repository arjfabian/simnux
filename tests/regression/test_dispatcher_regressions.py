"""Regression tests for CommandDispatcher assumptions.

Validates that the dispatcher correctly raises on unregistered commands
and succeeds after registration (foundational invariants).
"""

import pytest

from simnux.commands.dispatcher import CommandDispatcher
from simnux.commands.registry import CommandRegistry
from simnux.runtime.models import CommandResult


class TestRegressionDispatcherAssumptions:
    """Fundamental dispatcher invariants: fail fast on unknown, work on registered."""

    def test_dispatch_to_unregistered_command_raises(self):
        """Dispatching an unregistered command raises ``ValueError``."""
        registry = CommandRegistry()
        dispatcher = CommandDispatcher(registry=registry)
        with pytest.raises(ValueError, match="not registered"):
            dispatcher.dispatch("unknown", [])

    def test_dispatch_after_registration_succeeds(self):
        """Dispatching a registered command returns its result."""
        registry = CommandRegistry()
        from simnux.commands.runtime import SNXCommand

        class TestCmd(SNXCommand):
            name = "testcmd"
            def execute(self, args):
                return CommandResult(stdout="ok")

        registry.register(TestCmd(context=None))
        dispatcher = CommandDispatcher(registry=registry)
        result = dispatcher.dispatch("testcmd", [])
        assert result.stdout == ["ok"]
