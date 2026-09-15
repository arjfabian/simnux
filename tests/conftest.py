"""Shared fixtures and test infrastructure for SIMNUX test suite.

This module provides reusable pytest fixtures for:
- Scenario and session creation (factory fixtures)
- Filesystem base layers (hierarchy: fs_root_only -> fs_with_home -> fs_standard
  -> fs_rich)
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

from simnux.boot.app_factory import create_app
from simnux.boot.config import RuntimeConfig
from simnux.core.commands.dispatcher import CommandDispatcher
from simnux.core.commands.loader import CommandLoader
from simnux.core.commands.models import CommandContext
from simnux.core.commands.registry import CommandRegistry
from simnux.core.filesystem.models import PermissionPresets
from simnux.core.filesystem.models import SNXNode
from simnux.core.filesystem.vfs import SNXFileSystem
from simnux.core.runtime.runtime import SNXRuntime
from simnux.core.scenarios.models import SNXScenario
from simnux.core.shell.runtime import SNXShell
from simnux.security.execution.models import ExecutionContext
from simnux.security.groups.membership import SNXGroupMembership
from simnux.security.groups.models import SNXGroup
from simnux.security.users.models import SNXUser


ROOT_USER = SNXUser(0, "root")
ROOT_GROUP = SNXGroup(0, "root")
USER_OWNER = SNXUser(1001, "user")
USER_GROUP = SNXGroup(1001, "user")
ROOT_EXEC = ExecutionContext.for_user(ROOT_USER)
USER_EXEC = ExecutionContext.for_user(
    USER_OWNER,
    SNXGroupMembership.from_identities(
        {"root": ROOT_USER, "user": USER_OWNER},
        {"root": ROOT_GROUP, "user": USER_GROUP},
    ),
)


def pytest_configure(config):
    """Suppress PytestCollectionWarning for production Command class in
    condition.py.
    """
    config.addinivalue_line(
        "filterwarnings",
        "ignore::pytest.PytestCollectionWarning",
    )


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    """Reset the module-level slowapi limiter before each test.

    The ``Limiter`` in ``simnux.boot.middleware`` is a process-wide singleton,
    so its 30/min per-IP quota is shared across every test that hits the ASGI
    app. Without a reset, the aggregate requests in the API/integration suite
    exhaust the quota and later tests spuriously fail with HTTP 429.
    """
    from simnux.boot.middleware import limiter

    limiter.reset()


@pytest.fixture
def create_scenario():
    """Factory fixture for creating customizable SNXScenario instances.

    Returns a factory function that creates scenarios with a minimal 6-node
    filesystem: /, /home, /home/user, /root, and configurable starting_dir.

    Use this when you need a scenario with custom starting_dir or when testing
    scenario-related functionality.

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
            difficulty="Easy",
            hostname="simnux",
            users={
                "root": SNXUser(0, "root"),
                "user": SNXUser(1001, "user"),
            },
            groups={
                "root": SNXGroup(0, "root"),
                "user": SNXGroup(1001, "user"),
            },
            starting_dir=starting_dir,
            filesystem={
                "/": SNXNode(
                    path="/",
                    owner=ROOT_USER,
                    group=ROOT_GROUP,
                    content="",
                    is_directory=True,
                    permissions=PermissionPresets.DIRECTORY_DEFAULT,
                ),
                "/home": SNXNode(
                    path="/home",
                    owner=ROOT_USER,
                    group=ROOT_GROUP,
                    content="",
                    is_directory=True,
                    permissions=PermissionPresets.DIRECTORY_DEFAULT,
                ),
                "/home/user": SNXNode(
                    path="/home/user",
                    owner=USER_OWNER,
                    group=USER_GROUP,
                    content="",
                    is_directory=True,
                    permissions=PermissionPresets.DIRECTORY_DEFAULT,
                ),
                "/root": SNXNode(
                    path="/root",
                    owner=ROOT_USER,
                    group=ROOT_GROUP,
                    content="",
                    is_directory=True,
                    permissions=PermissionPresets.DIRECTORY_DEFAULT,
                ),
            },
        )

    return factory


@pytest.fixture
def create_session(create_scenario, test_logger):
    """Factory fixture for creating customizable SNXShell instances.

    Returns a factory function that creates shells using create_scenario as the
    scenario provider. Supports custom cwd and task counts.

    Use this when testing interaction state, snapshots, or when you need
    multiple shells with different scenarios for isolation testing.

    Args via factory:
        cwd: Starting current directory (default: "/home/user")
        starting_dir: Scenario starting dir (passed to create_scenario)
        identifier: Shell identifier (default: "reg-test")

    Returns:
        A factory function that creates SNXShell instances.

    Example:
        def test_shell_isolation(create_session):
            shell_a = create_session(identifier="a")
            shell_b = create_session(identifier="b")
            ...
    """

    def factory(**kw):
        scenario = create_scenario(
            starting_dir=kw.get(
                "starting_dir",
                "/home/user",
            )
        )

        filesystem = SNXFileSystem(base_layer=dict(scenario.filesystem))

        return SNXShell(
            scenario=scenario,
            execution_context=ExecutionContext.for_user(
                scenario.users["user"],
                SNXGroupMembership.from_identities(
                    scenario.users,
                    scenario.groups,
                ),
            ),
            current_directory=kw.get(
                "cwd",
                "/home/user",
            ),
            filesystem=filesystem,
            registry=CommandRegistry(),
            logger=test_logger,
            identifier=kw.get(
                "identifier",
                "reg-test",
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
            factory(base_layer=None, *, clock=None) -> SNXFileSystem

    Example:
        def test_filesystem_write(create_filesystem, fs_with_home):
            fs = create_filesystem(base_layer=fs_with_home)
            fs.write("/home/user/test.txt", content="test")
            ...
    """

    def factory(base_layer=None, *, clock=None):
        return SNXFileSystem(
            base_layer=dict(base_layer or minimal_fs),
            clock=clock,
        )

    return factory


@pytest.fixture
def fs_root_only():
    """Minimal filesystem base layer: just the root directory.

    Single-node filesystem for tests that need absolute minimal setup.
    Use this when testing path resolution edge cases or when testing scenarios
    that don't require home directories.

    Nodes:
        - / (directory)

    Returns:
        dict[str, SNXNode]: A single-node filesystem definition.
    """
    return {
        "/": SNXNode(
            path="/",
            owner=ROOT_USER,
            group=ROOT_GROUP,
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

    3-node filesystem for tests that need user home directory but not the full
    scenario setup. Useful for prompt renderer tests and path resolution tests
    involving home directories.

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
            owner=ROOT_USER,
            group=ROOT_GROUP,
            content="",
            is_directory=True,
            permissions=PermissionPresets.DIRECTORY_DEFAULT,
        ),
        "/home": SNXNode(
            path="/home",
            owner=ROOT_USER,
            group=ROOT_GROUP,
            content="",
            is_directory=True,
            permissions=PermissionPresets.DIRECTORY_DEFAULT,
        ),
        "/home/user": SNXNode(
            path="/home/user",
            owner=USER_OWNER,
            group=USER_GROUP,
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
        "/": SNXNode(
            path="/",
            owner=ROOT_USER,
            group=ROOT_GROUP,
            content="",
            is_directory=True,
            permissions=PermissionPresets.DIRECTORY_DEFAULT,
        ),
        "/home": SNXNode(
            path="/home",
            owner=ROOT_USER,
            group=ROOT_GROUP,
            content="",
            is_directory=True,
            permissions=PermissionPresets.DIRECTORY_DEFAULT,
        ),
        "/home/user": SNXNode(
            path="/home/user",
            owner=USER_OWNER,
            group=USER_GROUP,
            content="",
            is_directory=True,
            permissions=PermissionPresets.DIRECTORY_DEFAULT,
        ),
        "/home/user/notes.txt": SNXNode(
            path="/home/user/notes.txt",
            owner=USER_OWNER,
            group=USER_GROUP,
            content="hello world",
            is_directory=False,
            permissions=PermissionPresets.FILE_DEFAULT,
        ),
        "/etc": SNXNode(
            path="/etc",
            owner=ROOT_USER,
            group=ROOT_GROUP,
            content="",
            is_directory=True,
            permissions=PermissionPresets.DIRECTORY_DEFAULT,
        ),
        "/etc/hostname": SNXNode(
            path="/etc/hostname",
            owner=ROOT_USER,
            group=ROOT_GROUP,
            content="simnux-edge",
            is_directory=False,
            permissions=PermissionPresets.FILE_DEFAULT,
        ),
        "/var": SNXNode(
            path="/var",
            owner=ROOT_USER,
            group=ROOT_GROUP,
            content="",
            is_directory=True,
            permissions=PermissionPresets.DIRECTORY_DEFAULT,
        ),
        "/var/log": SNXNode(
            path="/var/log",
            owner=ROOT_USER,
            group=ROOT_GROUP,
            content="",
            is_directory=True,
            permissions=PermissionPresets.DIRECTORY_DEFAULT,
        ),
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

    10-node filesystem for overlay integrity tests and tests that need files
    like /etc/passwd and /etc/shadow for testing copy-on-write behavior and
    session isolation.

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

    Creates a logger with DEBUG level and a NullHandler to suppress output
    during tests. Use this when testing components that require a logger but
    don't need actual output verification.

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

    Creates a RuntimeConfig with log_path pointing to a file in pytest's
    temporary directory. Used by the runtime fixture.

    Returns:
        RuntimeConfig: Configuration with temporary log path.
    """
    return RuntimeConfig(log_path=str(tmp_path / "simnux_test.log"))


@pytest.fixture
def base_layer_rich(base_layer):
    """Extended base_layer with additional nodes for overlay integrity tests.

    Adds security-sensitive files to base_layer for testing copy-on-write
    overlay behavior. Tests that write to these files should verify that the
    base_layer remains unchanged (delta layer gets the mutations).

    Nodes added:
        - /etc/passwd: Simulated passwd file entry
        - /etc/shadow: Simulated shadow file entry
        - /home/user/secret.txt: Simulated flag/hidden content

    Returns:
        dict[str, SNXNode]: Extended filesystem definition.
    """
    return {
        **base_layer,
        "/etc/passwd": SNXNode(
            path="/etc/passwd",
            owner=ROOT_USER,
            group=ROOT_GROUP,
            content="root:x:0:0:root:/root:/bin/bash",
            is_directory=False,
            permissions=PermissionPresets.FILE_DEFAULT,
        ),
        "/etc/shadow": SNXNode(
            path="/etc/shadow",
            owner=ROOT_USER,
            group=ROOT_GROUP,
            content="root:!:20000:0:99999:7:::",
            is_directory=False,
            permissions=PermissionPresets.FILE_DEFAULT,
        ),
        "/home/user/secret.txt": SNXNode(
            path="/home/user/secret.txt",
            owner=USER_OWNER,
            group=USER_GROUP,
            content="FLAG{hidden}",
            is_directory=False,
            permissions=PermissionPresets.FILE_DEFAULT,
        ),
    }


@pytest.fixture
def filesystem(base_layer):
    """SNXFileSystem instance using the standard base_layer.

    Wraps base_layer in an SNXFileSystem instance. Use this for tests that need
    a ready-to-use filesystem rather than a base_layer dict.

    Returns:
        SNXFileSystem: Filesystem instance with standard base layer.
    """
    return SNXFileSystem(base_layer=dict(base_layer))


@pytest.fixture
def filesystem_rich(base_layer_rich):
    """SNXFileSystem instance using the extended base_layer_rich.

    Wraps base_layer_rich in an SNXFileSystem instance for overlay integrity
    tests and tests that need the extended file set.

    Returns:
        SNXFileSystem: Filesystem instance with extended base layer.
    """
    return SNXFileSystem(base_layer=dict(base_layer_rich))


@pytest.fixture
def base(base_layer_rich):
    """Alias for base_layer_rich - used by overlay integrity tests.

    Shorter alias for tests in test_overlay_integrity.py that reference this
    fixture by the 'base' name. Maintained for compatibility.

    Returns:
        dict[str, SNXNode]: Same as base_layer_rich.
    """
    return base_layer_rich


@pytest.fixture
def fs(filesystem_rich):
    """Alias for filesystem_rich - used by overlay integrity tests.

    Shorter alias for tests in test_overlay_integrity.py that reference this
    fixture by the 'fs' name. Maintained for compatibility.

    Returns:
        SNXFileSystem: Same as filesystem_rich.
    """
    return filesystem_rich


@pytest.fixture
def base_scenario(base_layer):
    """Standard test scenario using base_layer filesystem.

    Creates a SNXScenario with default test configuration and the standard
    7-node base_layer filesystem. Use this when you need a scenario for session
    or shell creation.

    Scenario details:
        - name: "TestScenario"
        - difficulty: "Easy"
        - user: "user"
        - hostname: "testhost"
        - starting_dir: "/home/user"

    Returns:
        SNXScenario: A configured scenario instance.
    """
    return SNXScenario(
        name="TestScenario",
        difficulty="Easy",
        hostname="testhost",
        users={
            "root": SNXUser(0, "root"),
            "user": SNXUser(1001, "user"),
        },
        groups={
            "root": SNXGroup(0, "root"),
            "user": SNXGroup(1001, "user"),
        },
        starting_dir="/home/user",
        filesystem=dict(base_layer),
    )


@pytest.fixture
def session(base_scenario, filesystem, test_logger):
    """Standard test shell using base_scenario and the filesystem fixture.

    Creates an SNXShell with a fixed identifier and base_scenario as the
    scenario, sharing the ``filesystem`` fixture instance. Use this for tests
    that need a ready-made interaction-state owner (the shell).

    Shell details:
        - identifier: "TestScenario"
        - scenario: base_scenario
        - current_directory: "/home/user"

    Returns:
        SNXShell: A configured shell instance.
    """
    return SNXShell(
        scenario=base_scenario,
        execution_context=ExecutionContext.for_user(
            base_scenario.users["user"],
            SNXGroupMembership.from_identities(
                base_scenario.users,
                base_scenario.groups,
            ),
        ),
        current_directory=base_scenario.starting_dir,
        filesystem=filesystem,
        registry=CommandRegistry(),
        logger=test_logger,
        identifier=base_scenario.name,
    )


@pytest.fixture
def runtime_shell(runtime):
    """Shell instance created via SNXRuntime with "hello" scenario.

    Creates a shell by calling runtime.create_session(). This is the preferred
    way to get a shell for e2e tests and tests that need the full runtime setup
    with all commands loaded.

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

    Creates a CommandContext instance that combines shell interaction state and
    filesystem for direct command execution. Use this when testing individual
    commands without the full shell infrastructure.

    Returns:
        CommandContext: Context for command execution.
    """
    return CommandContext(
        shell=session,
        filesystem=filesystem,
        execution_context=session.execution_context,
    )


@pytest.fixture
def registry():
    """Empty CommandRegistry instance.

    Creates a fresh CommandRegistry with no commands registered.
    Use this for testing registry operations like register(), get(), and
    list_commands().

    Returns:
        CommandRegistry: An empty registry instance.
    """
    return CommandRegistry()


@pytest.fixture
def dispatcher(registry):
    """CommandDispatcher using the empty registry fixture.

    Creates a CommandDispatcher instance bound to the provided registry.
    Use this for testing dispatch behavior when commands are registered vs.
    unregistered.

    Returns:
        CommandDispatcher: A dispatcher instance.
    """
    return CommandDispatcher(registry=registry)


@pytest.fixture
def populated_registry(session, filesystem, test_logger):
    """CommandRegistry with all standard commands loaded.

    Creates a registry and uses CommandLoader to load all available commands
    (cat, cd, echo, ls, pwd, touch, etc.). Use this when testing full command
    execution or when you need access to registered commands without a full
    shell.

    Returns:
        CommandRegistry: A registry with all standard commands.
    """
    registry = CommandRegistry()

    context = CommandContext(
        shell=session,
        filesystem=filesystem,
        execution_context=session.execution_context,
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

    Creates an SNXShell instance using the default session, filesystem, and
    test_logger fixtures, with all commands loaded via
    create_shell_with_commands(). This is the primary fixture for command unit
    tests.

    Uses the default session and filesystem fixtures, so tests that need custom
    filesystem setup should either:
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
    runtime.create_session(). Use this for e2e tests and for tests that need the
    runtime's session management capabilities.

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
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
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
