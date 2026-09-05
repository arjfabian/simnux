"""Test helper functions and utilities for SIMNUX test suite."""

import asyncio
import logging

from simnux.core.commands.dispatcher import CommandDispatcher
from simnux.core.commands.loader import CommandLoader
from simnux.core.commands.models import CommandContext
from simnux.core.commands.registry import CommandRegistry
from simnux.core.filesystem.models import PermissionPresets
from simnux.core.filesystem.models import SNXNode
from simnux.core.filesystem.vfs import SNXFileSystem
from simnux.core.runtime.models import ExitCode
from simnux.core.scenarios.models import SNXScenario
from simnux.core.shell.runtime import SNXShell
from simnux.security.groups.models import SNXGroup
from simnux.security.users.models import SNXUser


_ROOT_USER = SNXUser(0, "root")
_ROOT_GROUP = SNXGroup(0, "root")
_USER_OWNER = SNXUser(1001, "user")
_USER_GROUP = SNXGroup(1001, "user")


def _scratch_scenario() -> SNXScenario:
    """Minimal scenario with root + user identities and a home directory."""
    return SNXScenario(
        name="Test",
        difficulty="Easy",
        hostname="simnux",
        users={
            "root": _ROOT_USER,
            "user": _USER_OWNER,
        },
        groups={
            "root": _ROOT_GROUP,
            "user": _USER_GROUP,
        },
        starting_dir="/home/user",
        filesystem={
            "/": SNXNode(
                path="/",
                owner=_ROOT_USER,
                group=_ROOT_GROUP,
                content="",
                is_directory=True,
                permissions=PermissionPresets.DIRECTORY_DEFAULT,
            ),
            "/home": SNXNode(
                path="/home",
                owner=_ROOT_USER,
                group=_ROOT_GROUP,
                content="",
                is_directory=True,
                permissions=PermissionPresets.DIRECTORY_DEFAULT,
            ),
            "/home/user": SNXNode(
                path="/home/user",
                owner=_USER_OWNER,
                group=_USER_GROUP,
                content="",
                is_directory=True,
                permissions=PermissionPresets.DIRECTORY_DEFAULT,
            ),
        },
    )


def make_shell(
    filesystem: SNXFileSystem,
    logger: logging.Logger,
    registry: CommandRegistry | None = None,
    *,
    scenario: SNXScenario | None = None,
    user: SNXUser | None = None,
    current_directory: str | None = None,
    identifier: str | None = None,
) -> SNXShell:
    """Create an SNXShell with an empty or custom registry.

    For a shell with all standard commands, use create_shell_with_commands()
    or the shell_with_commands fixture.
    """
    scenario_ref = scenario or _scratch_scenario()

    if user is None:
        user = scenario_ref.users.get("user") or next(iter(scenario_ref.users.values()))

    return SNXShell(
        scenario=scenario_ref,
        user=user,
        current_directory=current_directory or scenario_ref.starting_dir,
        filesystem=filesystem,
        registry=registry or CommandRegistry(),
        logger=logger,
        identifier=identifier or scenario_ref.name,
    )


def create_shell_with_commands(
    shell: SNXShell,
    filesystem: SNXFileSystem,
    logger: logging.Logger,
) -> SNXShell:
    """Load all standard commands into *shell* via CommandLoader.

    Rebuilds the shell's registry (and dispatcher) so commands are available
    for direct ``shell.execute(...)`` calls.
    """
    registry = CommandRegistry()
    context = CommandContext(shell=shell, filesystem=filesystem)
    loader = CommandLoader(registry=registry, context=context, logger=logger)
    loader.load_all()

    shell.registry = registry
    shell.dispatcher = CommandDispatcher(registry=registry, limits=shell.limits)

    return shell


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
