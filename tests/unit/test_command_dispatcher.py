"""Tests for the CommandDispatcher dispatch layer.

Validates that command name resolution and delegation to registered
command instances works correctly, including error propagation and
registry isolation.
"""

import pytest

from simnux.commands.dispatcher import CommandDispatcher
from simnux.commands.registry import CommandRegistry
from simnux.commands.runtime import SNXCommand
from simnux.runtime.models import CommandResult, ExitCode


class _SimpleCommand(SNXCommand):
    name = "simple"

    def execute(self, args):
        return CommandResult(stdout=f"executed with {args}")


class _FailingCommand(SNXCommand):
    name = "fails"

    def execute(self, args):
        raise RuntimeError("something went wrong")


def make_registry(*commands):
    registry = CommandRegistry()

    for command_cls in commands:
        registry.register(command_cls(context=None))

    return registry


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

    def test_successful_dispatch(self, dispatcher):
        """Dispatch to a registered command returns its result with SUCCESS exit code."""
        result = dispatcher.dispatch("simple", ["a", "b"])

        assert result.stdout == ["executed with ['a', 'b']"]
        assert result.exit_code == ExitCode.SUCCESS

    def test_dispatch_empty_args(self, dispatcher):
        """Dispatch with an empty argument list should still succeed (boundary case)."""
        result = dispatcher.dispatch("simple", [])

        assert result.stdout == ["executed with []"]
        assert result.exit_code == ExitCode.SUCCESS


class TestCommandDispatcherErrors:
    """Error-handling dispatch scenarios.

    Verifies that missing commands raise ``ValueError`` and that
    exceptions thrown by command execution propagate correctly.
    """

    def test_missing_command_raises(self, dispatcher):
        """Dispatching an unregistered command raises ``ValueError`` (precondition enforcement)."""
        with pytest.raises(ValueError, match="not registered"):
            dispatcher.dispatch("nonexistent", [])

    def test_exception_propagation(self):
        """Exceptions raised inside command ``execute()`` propagate to the caller."""
        dispatcher = CommandDispatcher(
            registry=make_registry(
                _SimpleCommand,
                _FailingCommand,
            )
        )

        with pytest.raises(RuntimeError, match="something went wrong"):
            dispatcher.dispatch("fails", [])


class TestCommandDispatcherIsolation:
    """Ensures each ``CommandDispatcher`` instance operates on its own registry.

    Two dispatchers backed by different registries must not share state;
    a command available in one must not be visible in the other.
    """

    def test_dispatcher_different_registries_isolated(self):
        """Dispatchers with separate registries do not share command availability."""
        dispatcher1 = CommandDispatcher(
            registry=make_registry(_SimpleCommand)
        )

        result = dispatcher1.dispatch("simple", [])

        assert result.exit_code == ExitCode.SUCCESS

        dispatcher2 = CommandDispatcher(
            registry=make_registry()
        )

        with pytest.raises(ValueError):
            dispatcher2.dispatch("simple", [])
