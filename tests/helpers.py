"""Test helper functions and utilities for SIMNUX test suite."""

import asyncio
import logging

from simnux.commands.loader import CommandLoader
from simnux.commands.models import CommandContext
from simnux.commands.registry import CommandRegistry
from simnux.filesystem.vfs import SNXFileSystem
from simnux.runtime.models import ExitCode
from simnux.sessions.runtime import SNXSession
from simnux.shell.runtime import SNXShell


def make_shell(session, filesystem, logger, registry=None):
    """Create an SNXShell with an empty or custom registry.

    For a shell with all standard commands, use create_shell_with_commands()
    or the shell_with_commands fixture.
    """
    return SNXShell(
        session=session,
        filesystem=filesystem,
        registry=registry or CommandRegistry(),
        logger=logger,
    )


def create_shell_with_commands(
    session: SNXSession,
    filesystem: SNXFileSystem,
    logger: logging.Logger,
) -> SNXShell:
    """Create a shell with all standard commands loaded via CommandLoader."""
    registry = CommandRegistry()
    context = CommandContext(session=session, filesystem=filesystem)
    loader = CommandLoader(registry=registry, context=context, logger=logger)
    loader.load_all()
    return SNXShell(session=session, filesystem=filesystem, registry=registry, logger=logger)


def assert_success(result):
    """Assert result.exit_code == ExitCode.SUCCESS (0)."""
    assert result.exit_code == ExitCode.SUCCESS


def assert_not_success(result):
    """Assert result.exit_code != ExitCode.SUCCESS."""
    assert result.exit_code != ExitCode.SUCCESS


def assert_error(result):
    """Assert result.exit_code == ExitCode.ERROR (1)."""
    assert result.exit_code == ExitCode.ERROR


def assert_invalid_args(result):
    """Assert result.exit_code == ExitCode.INVALID_ARGUMENT (2)."""
    assert result.exit_code == ExitCode.INVALID_ARGUMENT


def stdout_text(result):
    """Extract stdout from a CommandResult as a newline-joined string."""
    return "\n".join(result.stdout or [])


def stderr_text(result):
    """Extract stderr from a CommandResult as a newline-joined string."""
    return "\n".join(result.stderr or [])


def api_stdout_text(data: dict) -> str:
    """Extract stdout from an API JSON response dict."""
    return "\n".join(data["stdout"])


def api_stderr_text(data: dict) -> str:
    """Extract stderr from an API JSON response dict."""
    return "\n".join(data["stderr"])


def drain_queue(queue: asyncio.Queue) -> list[str]:
    """Drain all non-None items from a queue, splitting each on newlines."""
    lines: list[str] = []
    while True:
        try:
            item = queue.get_nowait()
        except asyncio.QueueEmpty:
            break
        if item is not None:
            lines.extend(item.splitlines())
    return lines
