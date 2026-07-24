"""Tests for resource limits: VFS byte caps, script loop bounds, execution time."""

import asyncio
from unittest.mock import MagicMock

import pytest

from simnux.commands.errors import CommandError
from simnux.commands.models import CommandContext
from simnux.commands.registry import CommandRegistry
from simnux.commands.streams import QueueStreamWriter
from simnux.filesystem.models import PermissionPresets
from simnux.filesystem.models import SNXNode
from simnux.filesystem.vfs import SNXFileSystem
from simnux.init.config import LimitsConfig
from simnux.init.config import ScriptLimits
from simnux.init.config import VfsLimits
from simnux.runtime.models import ExitCode
from simnux.scripting.runner import ScriptRunner


# ── VFS byte caps ────────────────────────────────────────────────────────


class TestVfsFileByteLimit:
    """Single-file byte cap enforcement in write() and append()."""

    def test_write_within_limit(self, base_layer):
        """Write within max_file_bytes succeeds."""
        fs = SNXFileSystem(
            base_layer=dict(base_layer),
            max_file_bytes=100,
        )
        result = fs.write("/home/user/notes.txt", "hello")
        assert result.exit_code == ExitCode.SUCCESS

    def test_write_exceeds_file_limit(self, base_layer):
        """Write exceeding max_file_bytes returns DISK_QUOTA_EXCEEDED."""
        fs = SNXFileSystem(
            base_layer=dict(base_layer),
            max_file_bytes=5,
        )
        result = fs.write("/home/user/notes.txt", "hello world")
        assert result.exit_code == ExitCode.ERROR
        assert result.message == CommandError.DISK_QUOTA_EXCEEDED

    def test_append_exceeds_file_limit(self, base_layer):
        """Append that would exceed max_file_bytes returns DISK_QUOTA_EXCEEDED."""
        fs = SNXFileSystem(
            base_layer=dict(base_layer),
            max_file_bytes=10,
        )
        # Existing content is "hello world" (11 bytes) — already over limit,
        # but the check is on the *resulting* content.
        result = fs.append("/home/user/notes.txt", " extra")
        assert result.exit_code == ExitCode.ERROR
        assert result.message == CommandError.DISK_QUOTA_EXCEEDED

    def test_write_zero_limit_disables_check(self, base_layer):
        """max_file_bytes=0 disables the per-file check."""
        fs = SNXFileSystem(
            base_layer=dict(base_layer),
            max_file_bytes=0,
        )
        result = fs.write("/home/user/notes.txt", "x" * 10_000)
        assert result.exit_code == ExitCode.SUCCESS


class TestVfsTotalByteLimit:
    """Total byte cap across all files in a session."""

    def test_total_limit_enforced(self):
        """Write exceeding max_total_bytes returns DISK_QUOTA_EXCEEDED."""
        base = {
            "/": SNXNode(path="/", content="", is_directory=True,
                         permissions=PermissionPresets.DIRECTORY_DEFAULT),
            "/a": SNXNode(path="/a", content="aaa", is_directory=False,
                          permissions=PermissionPresets.FILE_DEFAULT),
        }
        fs = SNXFileSystem(
            base_layer=base,
            max_file_bytes=0,  # no per-file limit
            max_total_bytes=10,
        )
        # Write 7 bytes to /a (replacing 3) — total becomes 7, within limit
        result = fs.write("/a", "bbbbbbb")
        assert result.exit_code == ExitCode.SUCCESS

        # Write 11 bytes — projected total = 7 - 7 + 11 = 11 > 10
        result = fs.write("/a", "x" * 11)
        assert result.exit_code == ExitCode.ERROR
        assert result.message == CommandError.DISK_QUOTA_EXCEEDED

    def test_total_limitTracksAccumulation(self):
        """Multiple writes accumulate total bytes correctly."""
        base = {
            "/": SNXNode(path="/", content="", is_directory=True,
                         permissions=PermissionPresets.DIRECTORY_DEFAULT),
            "/a": SNXNode(path="/a", content="", is_directory=False,
                          permissions=PermissionPresets.FILE_DEFAULT),
            "/b": SNXNode(path="/b", content="", is_directory=False,
                          permissions=PermissionPresets.FILE_DEFAULT),
        }
        fs = SNXFileSystem(
            base_layer=base,
            max_file_bytes=0,
            max_total_bytes=20,
        )
        fs.write("/a", "12345")  # 5 bytes
        fs.write("/b", "67890")  # 5 bytes, total = 10
        result = fs.write("/a", "x" * 15)  # projected = 10 - 5 + 15 = 20, ok
        assert result.exit_code == ExitCode.SUCCESS

        result = fs.write("/b", "y" * 11)  # projected = 20 - 5 + 11 = 26, over
        assert result.exit_code == ExitCode.ERROR

    def test_total_limit_zero_disables(self):
        """max_total_bytes=0 disables the total check."""
        base = {
            "/": SNXNode(path="/", content="", is_directory=True,
                         permissions=PermissionPresets.DIRECTORY_DEFAULT),
            "/a": SNXNode(path="/a", content="", is_directory=False,
                          permissions=PermissionPresets.FILE_DEFAULT),
        }
        fs = SNXFileSystem(
            base_layer=base,
            max_total_bytes=0,
        )
        result = fs.write("/a", "x" * 100_000)
        assert result.exit_code == ExitCode.SUCCESS


# ── ScriptRunner loop bounds ─────────────────────────────────────────────


class _StubCommand:
    """Minimal command stub for ScriptRunner tests."""

    def __init__(self, name: str, exit_code: ExitCode = ExitCode.SUCCESS):
        self.name = name
        self.aliases: list[str] = []
        self.args: list[str] = []
        self._invoked_name = name
        self.parameters = None
        self.parsed_args = None
        self.action_type = 0

    async def execute(self, ctx, stdin, stdout, stderr):
        return ExitCode.SUCCESS


def _make_runner(limits: LimitsConfig) -> tuple[ScriptRunner, CommandContext]:
    """Create a ScriptRunner with the given limits and a minimal context."""
    registry = CommandRegistry()
    runner = ScriptRunner(registry, limits=limits)

    session = MagicMock()
    session.session_id = "test"
    session.current_directory = "/home/user"
    session.home_directory = "/home/user"
    session.environment = {}

    filesystem = MagicMock()
    filesystem.resolve_path.return_value = "/home/user"

    ctx = CommandContext(session=session, filesystem=filesystem)
    return runner, ctx


async def _run_script(runner, ctx, script: str) -> tuple[ExitCode, list[str]]:
    """Execute a script and return (exit_code, stderr_lines)."""
    stdin = MagicMock()
    stdout = QueueStreamWriter(asyncio.Queue())
    stderr = QueueStreamWriter(asyncio.Queue())

    result = await runner.execute(script, ctx, stdin, stdout, stderr)

    stderr_lines = []
    while not stderr._queue.empty():
        stderr_lines.append(stderr._queue.get_nowait())

    return result.exit_code, stderr_lines


class TestScriptLoopIterations:
    """while/for loops bounded by max_loop_iterations."""

    pytestmark = pytest.mark.asyncio

    async def test_while_infinite_loop_rejected(self):
        """A ``while true`` loop with a very low iteration limit is rejected."""
        limits = LimitsConfig(script=ScriptLimits(max_loop_iterations=5))
        runner, ctx = _make_runner(limits)

        # Register a "true" command that always succeeds
        true_cmd = _StubCommand("true")
        runner.registry.register(true_cmd)

        script = "while true\n  true\ndone"
        exit_code, stderr = await _run_script(runner, ctx, script)

        assert exit_code == ExitCode.ERROR
        assert any("exceeded maximum loop iterations" in line for line in stderr)

    async def test_for_infinite_word_list_rejected(self):
        """A ``for`` loop with many words and a low limit is rejected."""
        limits = LimitsConfig(script=ScriptLimits(max_loop_iterations=3))
        runner, ctx = _make_runner(limits)

        echo_cmd = _StubCommand("echo")
        runner.registry.register(echo_cmd)

        words = " ".join(str(i) for i in range(100))
        script = f"for i in {words}\n  echo $i\ndone"
        exit_code, stderr = await _run_script(runner, ctx, script)

        assert exit_code == ExitCode.ERROR
        assert any("exceeded maximum loop iterations" in line for line in stderr)

    async def test_for_within_limit_succeeds(self):
        """A ``for`` loop within the iteration limit succeeds."""
        limits = LimitsConfig(script=ScriptLimits(max_loop_iterations=10))
        runner, ctx = _make_runner(limits)

        echo_cmd = _StubCommand("echo")
        runner.registry.register(echo_cmd)

        script = "for i in a b c\n  echo $i\ndone"
        exit_code, _ = await _run_script(runner, ctx, script)

        assert exit_code == ExitCode.SUCCESS


class TestScriptExecutionTime:
    """Script execution bounded by max_execution_time_seconds."""

    pytestmark = pytest.mark.asyncio

    async def test_script_time_limit_rejected(self):
        """A script that would take longer than the limit is rejected."""
        import time as _time

        limits = LimitsConfig(script=ScriptLimits(
            max_execution_time_seconds=1,
            max_loop_iterations=1_000_000_000,
        ))
        runner, ctx = _make_runner(limits)

        class _SlowCommand:
            name = "slowwait"
            aliases = []
            args = []
            _invoked_name = "slowwait"
            parameters = None
            parsed_args = None
            action_type = 0

            async def execute(self, ctx, stdin, stdout, stderr):
                await asyncio.sleep(0.05)
                return ExitCode.SUCCESS

        runner.registry.register(_SlowCommand())

        script = "while true\n  slowwait\ndone"
        start = _time.monotonic()
        exit_code, stderr = await _run_script(runner, ctx, script)
        elapsed = _time.monotonic() - start

        assert exit_code == ExitCode.ERROR
        assert elapsed < 5, f"Script took too long: {elapsed:.1f}s"
        assert any("exceeded maximum execution time" in line for line in stderr)


class TestScriptLineLimit:
    """Script line count bounded by max_lines."""

    pytestmark = pytest.mark.asyncio

    async def test_script_line_limit_rejected(self):
        """A script exceeding max_lines is rejected immediately."""
        limits = LimitsConfig(script=ScriptLimits(max_lines=5))
        runner, ctx = _make_runner(limits)

        echo_cmd = _StubCommand("echo")
        runner.registry.register(echo_cmd)

        script = "\n".join("echo hello" for _ in range(10))
        exit_code, stderr = await _run_script(runner, ctx, script)

        assert exit_code == ExitCode.ERROR
        assert any("exceeded maximum line limit" in line for line in stderr)

    async def test_script_line_cap_rejects_before_running(self):
        """A script exceeding max_lines is rejected before line 1 runs."""
        max_lines = 5000
        limits = LimitsConfig(script=ScriptLimits(max_lines=max_lines))
        runner, ctx = _make_runner(limits)

        sentinel_called = False

        class _SentinelCommand:
            name = "sentinel"
            aliases = []
            args = []
            _invoked_name = "sentinel"
            parameters = None
            parsed_args = None
            action_type = 0

            async def execute(self, ctx, stdin, stdout, stderr):
                nonlocal sentinel_called
                sentinel_called = True
                return ExitCode.SUCCESS

        runner.registry.register(_SentinelCommand())

        script_lines = ["sentinel"] * (max_lines + 1)
        script = "\n".join(script_lines)
        exit_code, stderr = await _run_script(runner, ctx, script)

        assert exit_code == ExitCode.ERROR
        assert not sentinel_called, "No command should execute when line cap is exceeded"
        assert any("exceeded maximum line limit" in line for line in stderr)


# ── Stress tests ────────────────────────────────────────────────────────


class _EchoCommand:
    """Echo command that writes args to stdout (no trailing newline)."""

    name = "echo"
    aliases = []
    args = []
    _invoked_name = "echo"
    parameters = None
    parsed_args = None
    action_type = 0

    async def execute(self, ctx, stdin, stdout, stderr):
        await stdout.write(" ".join(self.args))
        return ExitCode.SUCCESS


class TestInfiniteWhileLoopWithTestCmd:
    """Infinite while loop using the real [ command."""

    pytestmark = pytest.mark.asyncio

    async def test_while_true_eq_1_loop_halts(self):
        """while [ 1 -eq 1 ] halts when max_loop_iterations is exceeded."""
        from simnux.commands.standard.condition import Command as TestCmd

        limits = LimitsConfig(script=ScriptLimits(max_loop_iterations=5))
        registry = CommandRegistry()
        runner = ScriptRunner(registry, limits=limits)
        registry.register(TestCmd(context=None))

        session = MagicMock()
        session.session_id = "test"
        session.current_directory = "/home/user"
        session.home_directory = "/home/user"
        session.environment = {}

        filesystem = MagicMock()
        filesystem.resolve_path.return_value = "/home/user"

        ctx = CommandContext(session=session, filesystem=filesystem)

        script = "while [ 1 -eq 1 ]\n  echo alive\ndone"
        exit_code, stderr = await _run_script(runner, ctx, script)

        assert exit_code == ExitCode.ERROR
        assert any("exceeded maximum loop iterations" in line for line in stderr)


class TestVfsQuotaBreachViaLoopAppend:
    """VFS quota enforcement when a script loop appends via >>."""

    def _make_real_fs_runner(
        self, limits: LimitsConfig, base_layer: dict[str, SNXNode],
    ) -> tuple[ScriptRunner, CommandContext, SNXFileSystem]:
        """Create a runner wired to a real SNXFileSystem."""
        fs = SNXFileSystem(
            base_layer=dict(base_layer),
            max_file_bytes=0,
            max_total_bytes=limits.vfs.max_total_bytes,
        )
        registry = CommandRegistry()
        runner = ScriptRunner(registry, limits=limits)
        registry.register(_EchoCommand())

        session = MagicMock()
        session.session_id = "test"
        session.current_directory = "/tmp"
        session.home_directory = "/home/user"
        session.environment = {}

        ctx = CommandContext(session=session, filesystem=fs)
        return runner, ctx, fs

    @pytest.mark.asyncio
    async def test_append_loop_rejects_when_total_exceeded(self):
        """Loop appending via >> halts when max_total_bytes is reached."""
        base = {
            "/": SNXNode(
                path="/", content="", is_directory=True,
                permissions=PermissionPresets.DIRECTORY_DEFAULT,
            ),
            "/tmp": SNXNode(
                path="/tmp", content="", is_directory=True,
                permissions=PermissionPresets.DIRECTORY_DEFAULT,
            ),
            "/data": SNXNode(
                path="/data", content="hello", is_directory=False,
                permissions=PermissionPresets.FILE_DEFAULT,
            ),
        }
        # max_total_bytes=8: "hello"=5 bytes, each "x"=1 byte → 3 appends OK, 4th rejected
        limits = LimitsConfig(vfs=VfsLimits(max_total_bytes=8))
        runner, ctx, fs = self._make_real_fs_runner(limits, base)

        script = "for i in 1 2 3 4 5 6 7 8 9 10\n  echo x >> /data\ndone"
        exit_code, stderr = await _run_script(runner, ctx, script)

        node = fs.get_node("/data")
        assert node is not None
        assert len(node.content) <= 8, (
            f"File content {node.content!r} exceeds total byte cap"
        )
        assert any("disk quota exceeded" in line for line in stderr)

    @pytest.mark.asyncio
    async def test_append_loop_preserves_existing_state(self):
        """Existing file content is preserved after quota breach."""
        base = {
            "/": SNXNode(
                path="/", content="", is_directory=True,
                permissions=PermissionPresets.DIRECTORY_DEFAULT,
            ),
            "/tmp": SNXNode(
                path="/tmp", content="", is_directory=True,
                permissions=PermissionPresets.DIRECTORY_DEFAULT,
            ),
            "/log": SNXNode(
                path="/log", content="AAA", is_directory=False,
                permissions=PermissionPresets.FILE_DEFAULT,
            ),
        }
        limits = LimitsConfig(vfs=VfsLimits(max_total_bytes=8))
        runner, ctx, fs = self._make_real_fs_runner(limits, base)

        # Write "AAA" + 5*5 bytes of "CCCCC" = 3+25=28, but total cap is 8
        # Each iteration appends "CCCCC" (5 bytes). After 1 iteration:
        # "AAACCCCC" = 8 bytes = exactly at cap. 2nd iteration rejected.
        script = "for i in 1 2 3 4 5\n  echo CCCCC >> /log\ndone"
        exit_code, _ = await _run_script(runner, ctx, script)

        node = fs.get_node("/log")
        assert node is not None
        assert node.content.startswith("AAA"), (
            f"Original content lost: {node.content!r}"
        )
        assert len(node.content.encode("utf-8")) <= 8

    @pytest.mark.asyncio
    async def test_append_loop_total_bytes_tracked_correctly(self):
        """VFS _current_total_bytes reflects only successful appends."""
        base = {
            "/": SNXNode(
                path="/", content="", is_directory=True,
                permissions=PermissionPresets.DIRECTORY_DEFAULT,
            ),
            "/tmp": SNXNode(
                path="/tmp", content="", is_directory=True,
                permissions=PermissionPresets.DIRECTORY_DEFAULT,
            ),
            "/a": SNXNode(
                path="/a", content="", is_directory=False,
                permissions=PermissionPresets.FILE_DEFAULT,
            ),
            "/b": SNXNode(
                path="/b", content="", is_directory=False,
                permissions=PermissionPresets.FILE_DEFAULT,
            ),
        }
        # /a starts empty, max_total_bytes=10
        limits = LimitsConfig(vfs=VfsLimits(max_total_bytes=10))
        runner, ctx, fs = self._make_real_fs_runner(limits, base)

        # Write 10 chars to /a then try 10 more to /b — 2nd should fail
        script = (
            "for i in 1 2 3 4 5 6 7 8 9 0\n  echo 1 >> /a\ndone"
            "\nfor i in 1 2 3 4 5 6 7 8 9 0\n  echo 2 >> /b\ndone"
        )
        exit_code, _ = await _run_script(runner, ctx, script)

        node_a = fs.get_node("/a")
        node_b = fs.get_node("/b")
        assert node_a is not None
        assert node_b is not None

        total = (
            len(node_a.content.encode("utf-8"))
            + len(node_b.content.encode("utf-8"))
        )
        assert total <= 10, (
            f"Total bytes {total} exceeds max_total_bytes=10"
        )


# ── LimitsConfig loader ──────────────────────────────────────────────────


class TestLimitsConfigLoader:
    """load_limits_config() with safe fallbacks."""

    def test_missing_file_returns_defaults(self, tmp_path):
        """When config/limits.yaml doesn't exist, defaults are returned."""
        from simnux.init.config import load_limits_config

        config = load_limits_config(tmp_path)
        assert config.vfs.max_file_bytes == 1_048_576
        assert config.vfs.max_total_bytes == 10_485_760
        assert config.script.max_loop_iterations == 10_000
        assert config.script.max_execution_time_seconds == 30
        assert config.script.max_lines == 5_000

    def test_partial_file_fills_defaults(self, tmp_path):
        """A partial YAML file fills in missing keys with defaults."""
        from simnux.init.config import load_limits_config

        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "limits.yaml").write_text(
            "vfs:\n  max_file_bytes: 500\n"
        )

        config = load_limits_config(tmp_path)
        assert config.vfs.max_file_bytes == 500
        assert config.vfs.max_total_bytes == 10_485_760  # default
        assert config.script.max_loop_iterations == 10_000  # default

    def test_invalid_yaml_returns_defaults(self, tmp_path):
        """Malformed YAML returns defaults without crashing."""
        from simnux.init.config import load_limits_config

        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "limits.yaml").write_text(": : : invalid yaml")

        config = load_limits_config(tmp_path)
        assert config.vfs.max_file_bytes == 1_048_576

    def test_default_path_finds_project_config(self):
        """load_limits_config() without project_root resolves to the actual project root."""
        from simnux.init.config import load_limits_config

        config = load_limits_config()
        assert config.vfs.max_file_bytes == 1_048_576
        assert config.vfs.max_total_bytes == 10_485_760


# ── FileStreamWriter error propagation ────────────────────────────────


class TestFileStreamWriterQuotaError:
    """FileStreamWriter captures and exposes VFS quota errors."""

    pytestmark = pytest.mark.asyncio

    async def test_append_quota_error_captured(self):
        """FileStreamWriter.last_error is set when append exceeds quota."""
        from simnux.commands.streams import FileStreamWriter

        base_layer = {
            "/tmp/test.txt": SNXNode(
                path="/tmp/test.txt",
                content="existing data here!!",  # 19 bytes
                is_directory=False,
                owner="user", group="user",
                permissions=PermissionPresets.FILE_DEFAULT,
            ),
        }
        fs = SNXFileSystem(
            base_layer=base_layer,
            max_file_bytes=25,
        )
        writer = FileStreamWriter(fs, "/tmp/test.txt", append=True)
        await writer.write("extra data that exceeds the limit")
        writer.close()
        assert writer.last_error is not None
        assert "quota" in writer.last_error.lower() or "DISK" in writer.last_error

    async def test_write_quota_error_captured(self):
        """FileStreamWriter.last_error is set when write exceeds quota."""
        from simnux.commands.streams import FileStreamWriter

        base_layer = {
            "/tmp/test.txt": SNXNode(
                path="/tmp/test.txt",
                content="hi",
                is_directory=False,
                owner="user", group="user",
                permissions=PermissionPresets.FILE_DEFAULT,
            ),
        }
        fs = SNXFileSystem(
            base_layer=base_layer,
            max_file_bytes=5,
        )
        writer = FileStreamWriter(fs, "/tmp/test.txt", append=False)
        await writer.write("this is way too long")
        writer.close()
        assert writer.last_error is not None

    async def test_successful_write_no_error(self):
        """FileStreamWriter.last_error is None on successful write."""
        from simnux.commands.streams import FileStreamWriter

        base_layer = {
            "/tmp/test.txt": SNXNode(
                path="/tmp/test.txt",
                content="",
                is_directory=False,
                owner="user", group="user",
                permissions=PermissionPresets.FILE_DEFAULT,
            ),
        }
        fs = SNXFileSystem(base_layer=base_layer, max_file_bytes=1000)
        writer = FileStreamWriter(fs, "/tmp/test.txt", append=True)
        await writer.write("hello")
        writer.close()
        assert writer.last_error is None

    async def test_append_quota_triggers_in_script_runner(self):
        """Append that hits per-file limit during script execution returns ERROR."""
        registry = CommandRegistry()
        limits = LimitsConfig(vfs=VfsLimits(max_file_bytes=30))
        runner = ScriptRunner(registry, limits=limits)
        registry.register(_EchoCommand())

        base_layer = {
            "/tmp/q.txt": SNXNode(
                path="/tmp/q.txt",
                content="existing",  # 8 bytes
                is_directory=False,
                owner="user", group="user",
                permissions=PermissionPresets.FILE_DEFAULT,
            ),
        }
        fs = SNXFileSystem(base_layer=base_layer, max_file_bytes=30)

        session = MagicMock()
        session.session_id = "test"
        session.current_directory = "/home/user"
        session.home_directory = "/home/user"
        session.environment = {}
        ctx = CommandContext(session=session, filesystem=fs)

        stdin = MagicMock()
        stdout = QueueStreamWriter(asyncio.Queue())
        stderr = QueueStreamWriter(asyncio.Queue())
        # Two appends: first adds 10 bytes (total 18), second adds 15 (total 33 > 30)
        script = (
            'echo "1234567890" >> /tmp/q.txt\n'
            'echo "123456789012345" >> /tmp/q.txt\n'
        )
        result = await runner.execute(script, ctx, stdin, stdout, stderr)
        # Second append exceeds 30-byte limit → runner should report error
        assert result.exit_code == ExitCode.ERROR

        stderr_lines = []
        while not stderr._queue.empty():
            stderr_lines.append(stderr._queue.get_nowait())
        assert any("disk quota exceeded" in line for line in stderr_lines)
