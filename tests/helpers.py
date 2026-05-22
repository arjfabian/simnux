"""Test helper functions and utilities for SIMNUX test suite.

This module provides reusable helpers for:
- Shell creation (with and without commands loaded)
- Result assertion helpers (exit code checking)
- Output extraction helpers (stdout/stderr from CommandResult and API responses)

Two categories of helpers exist:
1. Shell helpers: make_shell(), create_shell_with_commands()
2. Assertion helpers: assert_success(), assert_error(), etc.
3. Text extraction: stdout_text(), stderr_text(), api_stdout_text(), etc.
"""

import logging

from simnux.commands.loader import CommandLoader
from simnux.commands.models import CommandContext
from simnux.commands.registry import CommandRegistry
from simnux.filesystem.vfs import SNXFileSystem
from simnux.runtime.models import ExitCode
from simnux.sessions.runtime import SNXSession
from simnux.shell.runtime import SNXShell


def make_shell(session, filesystem, logger, registry=None):
    """Create an SNXShell instance with an empty or custom registry.

    Creates a shell without loading any commands. Use this when:
    - Testing registry operations directly
    - Testing custom command registration
    - You need full control over which commands are available

    For a shell with all standard commands pre-loaded, use
    create_shell_with_commands() or the shell_with_commands fixture.

    Args:
        session: The SNXSession instance for context (determines cwd, etc.)
        filesystem: The SNXFileSystem instance for file operations
        logger: A logging.Logger instance for shell operations
        registry: Optional CommandRegistry instance. If None, creates
            a new empty registry (no commands registered).

    Returns:
        SNXShell: An initialized shell instance.

    Example:
        def test_custom_command(make_shell, session, filesystem, test_logger):
            registry = CommandRegistry()
            registry.register(MyCustomCommand())
            shell = make_shell(session, filesystem, test_logger, registry)
            result = shell.execute("mycommand")
            ...
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
    """Create a shell with all standard commands loaded.

    Flexible alternative to the `shell_with_commands` fixture.
    Use this when you need a shell with custom session/filesystem setup,
    or when testing from regression tests that use the factory fixtures.

    Uses CommandLoader to discover and load all available commands
    (cat, cd, echo, ls, pwd, touch, etc.). The loaded commands depend
    on what's available in simnux.commands and what CommandLoader discovers.

    This is the same logic used by the shell_with_commands fixture, but
    without the fixture's dependency on specific session/filesystem fixtures.

    Args:
        session: The session to use (determines cwd, scenario, etc.)
        filesystem: The VFS instance for file operations
        logger: Logger for command loading and shell operations

    Returns:
        SNXShell: An initialized shell with all standard commands loaded.

    Example:
        def test_snapshot_shell(create_session, fs_with_home, test_logger):
            session = create_session(session_id="custom-id")
            fs = SNXFileSystem(base_layer=fs_with_home)
            shell = create_shell_with_commands(session, fs, test_logger)
            result = shell.execute("touch /home/user/test.txt")
            ...

    See Also:
        shell_with_commands: Fixture version using default session/filesystem
        make_shell: Create shell with custom or empty registry
    """
    registry = CommandRegistry()
    context = CommandContext(session=session, filesystem=filesystem)
    loader = CommandLoader(registry=registry, context=context, logger=logger)
    loader.load_all()
    return SNXShell(session=session, filesystem=filesystem, registry=registry, logger=logger)


def assert_success(result):
    """Assert that a CommandResult has exit code SUCCESS (0).

    Use this for tests where a command should succeed. Combines well with
    stdout_text() or stderr_text() for additional assertions.

    Args:
        result: CommandResult instance returned by shell.execute()

    Raises:
        AssertionError: If result.exit_code != ExitCode.SUCCESS

    Example:
        result = shell.execute("echo hello")
        assert_success(result)
        assert "hello" in stdout_text(result)
    """
    assert result.exit_code == ExitCode.SUCCESS


def assert_not_success(result):
    """Assert that a CommandResult does NOT have exit code SUCCESS (0).

    Use this for negative tests where a command should fail, but the
    specific error code doesn't matter. For specific error codes, use
    assert_error() or assert_invalid_args().

    Args:
        result: CommandResult instance returned by shell.execute()

    Raises:
        AssertionError: If result.exit_code == ExitCode.SUCCESS

    Example:
        result = shell.execute("cat nonexistent_file")
        assert_not_success(result)
    """
    assert result.exit_code != ExitCode.SUCCESS


def assert_error(result):
    """Assert that a CommandResult has exit code ERROR (1).

    Use this for general command failures that return exit code 1.
    For invalid argument errors, use assert_invalid_args().

    Args:
        result: CommandResult instance returned by shell.execute()

    Raises:
        AssertionError: If result.exit_code != ExitCode.ERROR

    Example:
        result = shell.execute("cat nonexistent_file")
        assert_error(result)
        assert "No such file" in stderr_text(result)
    """
    assert result.exit_code == ExitCode.ERROR


def assert_invalid_args(result):
    """Assert that a CommandResult has exit code INVALID_ARGUMENT (2).

    Use this for commands that fail due to invalid arguments:
    - Missing required operands (e.g., `touch` with no files)
    - Too many arguments (e.g., `pwd /etc`)
    - Invalid option combinations

    Args:
        result: CommandResult instance returned by shell.execute()

    Raises:
        AssertionError: If result.exit_code != ExitCode.INVALID_ARGUMENT

    Example:
        result = shell.execute("touch")  # Missing operand
        assert_invalid_args(result)
        assert "missing file operand" in stderr_text(result)
    """
    assert result.exit_code == ExitCode.INVALID_ARGUMENT


def stdout_text(result):
    """Extract stdout as a single string from a CommandResult.

    Combines the stdout list into a single newline-separated string.
    Use this with CommandResult objects returned by shell.execute().

    For API JSON responses (response.json()), use api_stdout_text() instead.

    Handles None values gracefully by treating them as empty output.

    Args:
        result: CommandResult instance with stdout: list[str] attribute

    Returns:
        str: Newline-joined stdout, or empty string if stdout is None/empty.

    Example:
        result = shell.execute("echo hello && echo world")
        assert "hello" in stdout_text(result)
        assert "world" in stdout_text(result)

    See Also:
        stderr_text: Same for stderr
        api_stdout_text: For API JSON response dicts
    """
    return "\n".join(result.stdout or [])


def stderr_text(result):
    """Extract stderr as a single string from a CommandResult.

    Combines the stderr list into a single newline-separated string.
    Use this with CommandResult objects returned by shell.execute().

    For API JSON responses (response.json()), use api_stderr_text() instead.

    Handles None values gracefully by treating them as empty output.

    Args:
        result: CommandResult instance with stderr: list[str] attribute

    Returns:
        str: Newline-joined stderr, or empty string if stderr is None/empty.

    Example:
        result = shell.execute("cat nonexistent_file")
        assert_error(result)
        assert "No such file" in stderr_text(result)

    See Also:
        stdout_text: Same for stdout
        api_stderr_text: For API JSON response dicts
    """
    return "\n".join(result.stderr or [])


def api_stdout_text(data: dict) -> str:
    """Extract stdout from an API JSON response dictionary.

    For use in API route tests (test_api_routes.py) where responses
    come from response.json() rather than shell.execute().

    Expects the dict to have a "stdout" key containing a list of strings.

    Args:
        data: Dictionary from response.json() with "stdout" key

    Returns:
        str: Newline-joined stdout from the response.

    Example:
        response = client.post("/execute", json={"command": "echo hello"})
        data = response.json()
        assert "hello" in api_stdout_text(data)
        assert api_stdout_text(data) == "hello"

    See Also:
        api_stderr_text: Same for stderr
        stdout_text: For CommandResult objects
    """
    return "\n".join(data["stdout"])


def api_stderr_text(data: dict) -> str:
    """Extract stderr from an API JSON response dictionary.

    For use in API route tests (test_api_routes.py) where responses
    come from response.json() rather than shell.execute().

    Expects the dict to have a "stderr" key containing a list of strings.

    Args:
        data: Dictionary from response.json() with "stderr" key

    Returns:
        str: Newline-joined stderr from the response.

    Example:
        response = client.post("/execute", json={"command": "cat missing"})
        data = response.json()
        assert "No such file" in api_stderr_text(data)

    See Also:
        api_stdout_text: Same for stdout
        stderr_text: For CommandResult objects
    """
    return "\n".join(data["stderr"])
