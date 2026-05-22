"""Shared fixtures and test infrastructure for SIMNUX test suite.

This module provides reusable pytest fixtures for:
- Scenario and session creation (factory fixtures)
- Filesystem base layers (hierarchy: fs_root_only -> fs_with_home -> fs_standard -> fs_rich)
- Command registry and dispatcher setup
- Shell instances with loaded commands
- HTTP API test client

All fixtures are designed to be composable and follow the backend's
verb-object naming convention for consistency.
"""

import logging

from httpx import ASGITransport
from httpx import AsyncClient
import pytest
import pytest_asyncio

from simnux.commands.dispatcher import CommandDispatcher
from simnux.commands.loader import CommandLoader
from simnux.commands.models import CommandContext
from simnux.commands.registry import CommandRegistry
from simnux.filesystem.models import PermissionPresets
from simnux.filesystem.models import SNXNode
from simnux.filesystem.vfs import SNXFileSystem
from simnux.init.app_factory import create_app
from simnux.init.config import RuntimeConfig
from simnux.runtime.runtime import SNXRuntime
from simnux.scenarios.models import SNXScenario
from simnux.sessions.runtime import SNXSession


@pytest.fixture
def create_scenario():
    """Factory fixture for creating customizable SNXScenario instances.

    Returns a factory function that creates scenarios with a minimal 6-node
    filesystem: /, /home, /home/user, /root, and configurable starting_dir.

    Use this when you need a scenario with custom starting_dir or when
    testing scenario-related functionality.

    Returns:
        A factory function with signature:
            factory(starting_dir="/home/user") -> SNXScenario

    Example:
        def test_something(create_scenario):
            scenario = create_scenario(starting_dir="/custom/path")
            ...
    """
    def factory(starting_dir="/home/user"):
        return SNXScenario(
            name="Regression",
            motd="Test",
            difficulty="Easy",
            username="user",
            hostname="simnux",
            starting_dir=starting_dir,
            filesystem={
                "/": SNXNode(
                    path="/",
                    content="",
                    is_directory=True,
                    permissions=PermissionPresets.DIRECTORY_DEFAULT,
                ),
                "/home": SNXNode(
                    path="/home",
                    content="",
                    is_directory=True,
                    permissions=PermissionPresets.DIRECTORY_DEFAULT,
                ),
                "/home/user": SNXNode(
                    path="/home/user",
                    content="",
                    is_directory=True,
                    permissions=PermissionPresets.DIRECTORY_DEFAULT,
                ),
                "/root": SNXNode(
                    path="/root",
                    content="",
                    is_directory=True,
                    permissions=PermissionPresets.DIRECTORY_DEFAULT,
                ),
            },
        )

    return factory


@pytest.fixture
def create_session(create_scenario):
    """Factory fixture for creating customizable SNXSession instances.

    Returns a factory function that creates sessions using create_scenario
    as the scenario provider. Supports custom session_id, cwd, and task counts.

    Use this when testing session persistence, snapshots, or when you need
    multiple sessions with different IDs for isolation testing.

    Args via factory:
        session_id: Custom session identifier (default: "reg-test")
        cwd: Starting current directory (default: "/home/user")
        starting_dir: Scenario starting dir (passed to create_scenario)
        tasks_total: Total tasks in scenario (default: 0)
        tasks_completed: Completed tasks (default: 0)

    Returns:
        A factory function that creates SNXSession instances.

    Example:
        def test_session_isolation(create_session):
            session_a = create_session(session_id="a")
            session_b = create_session(session_id="b")
            ...
    """
    def factory(**kw):
        scenario = create_scenario(
            starting_dir=kw.get(
                "starting_dir",
                "/home/user",
            )
        )

        return SNXSession(
            session_id=kw.get(
                "session_id",
                "reg-test",
            ),
            scenario=scenario,
            current_directory=kw.get(
                "cwd",
                "/home/user",
            ),
            tasks_total=kw.get(
                "tasks_total",
                0,
            ),
            tasks_completed=kw.get(
                "tasks_completed",
                0,
            ),
        )

    return factory


@pytest.fixture
def create_filesystem(minimal_fs):
    """Factory fixture for creating customizable SNXFileSystem instances.

    Returns a factory function that creates filesystems from optional base_layer
    dicts. If no base_layer is provided, uses fs_root_only (via minimal_fs).

    Use this when you need an SNXFileSystem instance with custom base layers
    for testing filesystem operations.

    Returns:
        A factory function with signature:
            factory(base_layer=None) -> SNXFileSystem

    Example:
        def test_filesystem_write(create_filesystem, fs_with_home):
            fs = create_filesystem(base_layer=fs_with_home)
            fs.write("/home/user/test.txt", content="test")
            ...
    """
    def factory(base_layer=None):
        return SNXFileSystem(
            base_layer=dict(base_layer or minimal_fs)
        )
    return factory


@pytest.fixture
def fs_root_only():
    """Minimal filesystem base layer: just the root directory.

    Single-node filesystem for tests that need absolute minimal setup.
    Use this when testing path resolution edge cases or when testing
    scenarios that don't require home directories.

    Nodes:
        - / (directory)

    Returns:
        dict[str, SNXNode]: A single-node filesystem definition.
    """
    return {
        "/": SNXNode(
            path="/",
            content="",
            is_directory=True,
            permissions=PermissionPresets.DIRECTORY_DEFAULT,
        ),
    }


@pytest.fixture
def minimal_fs(fs_root_only):
    """Deprecated alias for fs_root_only. Use fs_root_only instead.

    Maintained for backward compatibility with older tests.
    Prefer fs_root_only for clearer intent.

    Returns:
        dict[str, SNXNode]: Same as fs_root_only.
    """
    return fs_root_only


@pytest.fixture
def fs_with_home():
    """Filesystem base layer with basic home directory structure.

    3-node filesystem for tests that need user home directory but not
    the full scenario setup. Useful for prompt renderer tests and
    path resolution tests involving home directories.

    Nodes:
        - / (directory)
        - /home (directory)
        - /home/user (directory)

    Returns:
        dict[str, SNXNode]: A 3-node filesystem definition.
    """
    return {
        "/": SNXNode(
            path="/",
            content="",
            is_directory=True,
            permissions=PermissionPresets.DIRECTORY_DEFAULT,
        ),
        "/home": SNXNode(
            path="/home",
            content="",
            is_directory=True,
            permissions=PermissionPresets.DIRECTORY_DEFAULT,
        ),
        "/home/user": SNXNode(
            path="/home/user",
            content="",
            is_directory=True,
            permissions=PermissionPresets.DIRECTORY_DEFAULT,
        ),
    }


@pytest.fixture
def base_layer():
    """Standard 7-node test filesystem base layer.

    Rich filesystem for command tests and general-purpose testing.
    Includes common directories and a sample file for reading tests.

    Nodes:
        - / (directory)
        - /home (directory)
        - /home/user (directory)
        - /home/user/notes.txt (file, content: "hello world")
        - /etc (directory)
        - /etc/hostname (file, content: "simnux-edge")
        - /var (directory)
        - /var/log (directory)

    Returns:
        dict[str, SNXNode]: A 7-node filesystem definition.
    """
    return {
        "/": SNXNode(path="/", content="", is_directory=True, permissions=PermissionPresets.DIRECTORY_DEFAULT),
        "/home": SNXNode(path="/home", content="", is_directory=True, permissions=PermissionPresets.DIRECTORY_DEFAULT),
        "/home/user": SNXNode(path="/home/user", content="", is_directory=True, permissions=PermissionPresets.DIRECTORY_DEFAULT),
        "/home/user/notes.txt": SNXNode(path="/home/user/notes.txt", content="hello world", is_directory=False, permissions=PermissionPresets.FILE_DEFAULT),
        "/etc": SNXNode(path="/etc", content="", is_directory=True, permissions=PermissionPresets.DIRECTORY_DEFAULT),
        "/etc/hostname": SNXNode(path="/etc/hostname", content="simnux-edge", is_directory=False, permissions=PermissionPresets.FILE_DEFAULT),
        "/var": SNXNode(path="/var", content="", is_directory=True, permissions=PermissionPresets.DIRECTORY_DEFAULT),
        "/var/log": SNXNode(path="/var/log", content="", is_directory=True, permissions=PermissionPresets.DIRECTORY_DEFAULT),
    }


@pytest.fixture
def fs_standard(base_layer):
    """Standard 7-node test filesystem (alias for base_layer).

    Semantic alias for base_layer following the fs_* naming convention.
    Use this when testing command behavior or when you need a realistic
    filesystem structure with common directories.

    Returns:
        dict[str, SNXNode]: Same as base_layer.
    """
    return base_layer


@pytest.fixture
def fs_rich(base_layer_rich):
    """Extended filesystem with security-sensitive files.

    10-node filesystem for overlay integrity tests and tests that need
    files like /etc/passwd and /etc/shadow for testing copy-on-write
    behavior and session isolation.

    Nodes (extends base_layer):
        - /etc/passwd (file, content: "root:x:0:0:root:/root:/bin/bash")
        - /etc/shadow (file, content: "root:!:20000:0:99999:7:::")
        - /home/user/secret.txt (file, content: "FLAG{hidden}")

    Returns:
        dict[str, SNXNode]: A 10-node filesystem definition.
    """
    return base_layer_rich


@pytest.fixture
def test_logger():
    """Null logger for tests that need a logging.Logger instance.

    Creates a logger with DEBUG level and a NullHandler to suppress
    output during tests. Use this when testing components that require
    a logger but don't need actual output verification.

    Returns:
        logging.Logger: A configured logger instance.
    """
    logger = logging.getLogger("simnux_test")

    logger.setLevel(logging.DEBUG)

    logger.handlers.clear()
    logger.addHandler(logging.NullHandler())

    return logger


@pytest.fixture
def runtime_config(tmp_path):
    """Runtime configuration using a temporary log file.

    Creates a RuntimeConfig with log_path pointing to a file in
    pytest's temporary directory. Used by the runtime fixture.

    Returns:
        RuntimeConfig: Configuration with temporary log path.
    """
    return RuntimeConfig(
        log_path=str(tmp_path / "simnux_test.log")
    )


@pytest.fixture
def base_layer_rich(base_layer):
    """Extended base_layer with additional nodes for overlay integrity tests.

    Adds security-sensitive files to base_layer for testing copy-on-write
    overlay behavior. Tests that write to these files should verify that
    the base_layer remains unchanged (delta layer gets the mutations).

    Nodes added:
        - /etc/passwd: Simulated passwd file entry
        - /etc/shadow: Simulated shadow file entry
        - /home/user/secret.txt: Simulated flag/hidden content

    Returns:
        dict[str, SNXNode]: Extended filesystem definition.
    """
    return {
        **base_layer,
        "/etc/passwd": SNXNode(path="/etc/passwd", content="root:x:0:0:root:/root:/bin/bash", is_directory=False, permissions=PermissionPresets.FILE_DEFAULT),
        "/etc/shadow": SNXNode(path="/etc/shadow", content="root:!:20000:0:99999:7:::", is_directory=False, permissions=PermissionPresets.FILE_DEFAULT),
        "/home/user/secret.txt": SNXNode(path="/home/user/secret.txt", content="FLAG{hidden}", is_directory=False, permissions=PermissionPresets.FILE_DEFAULT),
    }


@pytest.fixture
def filesystem(base_layer):
    """SNXFileSystem instance using the standard base_layer.

    Wraps base_layer in an SNXFileSystem instance. Use this for tests
    that need a ready-to-use filesystem rather than a base_layer dict.

    Returns:
        SNXFileSystem: Filesystem instance with standard base layer.
    """
    return SNXFileSystem(base_layer=dict(base_layer))


@pytest.fixture
def filesystem_rich(base_layer_rich):
    """SNXFileSystem instance using the extended base_layer_rich.

    Wraps base_layer_rich in an SNXFileSystem instance for overlay
    integrity tests and tests that need the extended file set.

    Returns:
        SNXFileSystem: Filesystem instance with extended base layer.
    """
    return SNXFileSystem(base_layer=dict(base_layer_rich))


@pytest.fixture
def base(base_layer_rich):
    """Alias for base_layer_rich - used by overlay integrity tests.

    Shorter alias for tests in test_overlay_integrity.py that reference
    this fixture by the 'base' name. Maintained for compatibility.

    Returns:
        dict[str, SNXNode]: Same as base_layer_rich.
    """
    return base_layer_rich


@pytest.fixture
def fs(filesystem_rich):
    """Alias for filesystem_rich - used by overlay integrity tests.

    Shorter alias for tests in test_overlay_integrity.py that reference
    this fixture by the 'fs' name. Maintained for compatibility.

    Returns:
        SNXFileSystem: Same as filesystem_rich.
    """
    return filesystem_rich


@pytest.fixture
def base_scenario(base_layer):
    """Standard test scenario using base_layer filesystem.

    Creates a SNXScenario with default test configuration and the
    standard 7-node base_layer filesystem. Use this when you need
    a scenario for session or shell creation.

    Scenario details:
        - name: "TestScenario"
        - motd: "Welcome to SIMNUX Test"
        - difficulty: "Easy"
        - username: "testuser"
        - hostname: "testhost"
        - starting_dir: "/home/user"

    Returns:
        SNXScenario: A configured scenario instance.
    """
    return SNXScenario(
        name="TestScenario",
        motd="Welcome to SIMNUX Test",
        difficulty="Easy",
        username="testuser",
        hostname="testhost",
        starting_dir="/home/user",
        filesystem=dict(base_layer),
    )


@pytest.fixture
def session(base_scenario):
    """Standard test session using base_scenario.

    Creates an SNXSession with a fixed session_id and base_scenario
    as the scenario. Use this for tests that need a ready-made session
    without special configuration.

    Session details:
        - session_id: "test-session-id"
        - scenario: base_scenario
        - current_directory: "/home/user"

    Returns:
        SNXSession: A configured session instance.
    """
    return SNXSession(
        session_id="test-session-id",
        scenario=base_scenario,
        current_directory=base_scenario.starting_dir,
    )


@pytest.fixture
def runtime_shell(runtime):
    """Shell instance created via SNXRuntime with "hello" scenario.

    Creates a shell by calling runtime.create_session(). This is the
    preferred way to get a shell for e2e tests and tests that need
    the full runtime setup with all commands loaded.

    Uses a fixed UUID for session_id to maintain test determinism.

    Returns:
        SNXShell: A fully initialized shell with commands loaded.
    """
    return runtime.create_session(
        scenario_name="hello",
        session_id="53494d4e-5558-4202-a13d-204c494e5558",
    )


@pytest.fixture
def command_context(session, filesystem):
    """CommandContext for executing commands without a full shell.

    Creates a CommandContext instance that combines session and filesystem
    for direct command execution. Use this when testing individual commands
    without the full shell infrastructure.

    Returns:
        CommandContext: Context for command execution.
    """
    return CommandContext(session=session, filesystem=filesystem)


@pytest.fixture
def registry():
    """Empty CommandRegistry instance.

    Creates a fresh CommandRegistry with no commands registered.
    Use this for testing registry operations like register(), get(),
    and list_commands().

    Returns:
        CommandRegistry: An empty registry instance.
    """
    return CommandRegistry()


@pytest.fixture
def dispatcher(registry):
    """CommandDispatcher using the empty registry fixture.

    Creates a CommandDispatcher instance bound to the provided registry.
    Use this for testing dispatch behavior when commands are registered
    vs. unregistered.

    Returns:
        CommandDispatcher: A dispatcher instance.
    """
    return CommandDispatcher(registry=registry)


@pytest.fixture
def populated_registry(session, filesystem, test_logger):
    """CommandRegistry with all standard commands loaded.

    Creates a registry and uses CommandLoader to load all available
    commands (cat, cd, echo, ls, pwd, touch, etc.). Use this when
    testing full command execution or when you need access to
    registered commands without a full shell.

    Returns:
        CommandRegistry: A registry with all standard commands.
    """
    registry = CommandRegistry()

    context = CommandContext(
        session=session,
        filesystem=filesystem,
    )

    loader = CommandLoader(
        registry=registry,
        context=context,
        logger=test_logger,
    )

    loader.load_all()

    return registry


@pytest.fixture
def shell_with_commands(
    session,
    filesystem,
    test_logger,
):
    """Shell with all standard commands loaded using default fixtures.

    Creates an SNXShell instance using the default session, filesystem,
    and test_logger fixtures, with all commands loaded via
    create_shell_with_commands(). This is the primary fixture for
    command unit tests.

    Uses the default session and filesystem fixtures, so tests that
    need custom filesystem setup should either:
    1. Override session/filesystem fixtures, or
    2. Use create_shell_with_commands() directly

    Returns:
        SNXShell: A shell with all standard commands loaded.
    """
    from tests.helpers import create_shell_with_commands
    return create_shell_with_commands(session, filesystem, test_logger)


@pytest.fixture
def runtime(test_logger, runtime_config):
    """SNXRuntime instance for creating shells with "hello" scenario.

    Creates a full SNXRuntime instance that can create sessions via
    runtime.create_session(). Use this for e2e tests and for tests
    that need the runtime's session management capabilities.

    Returns:
        SNXRuntime: A configured runtime instance.
    """
    return SNXRuntime(logger=test_logger, config=runtime_config)


@pytest_asyncio.fixture
async def api_client(app):
    """Async HTTP client for testing FastAPI routes.

    Creates an httpx.AsyncClient configured to test the ASGI app.
    Use this with pytest-asyncio for testing API endpoints in
    test_api_routes.py.

    Yields:
        httpx.AsyncClient: Client configured for app testing.
    """
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
def app():
    """SIMNUX FastAPI application instance.

    Creates the FastAPI app via create_app() for API route testing.
    Used by the api_client fixture to make test requests.

    Returns:
        FastAPI: The configured application instance.
    """
    return create_app()
