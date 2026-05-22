"""End-to-end tests for full shell command workflows.

Exercises realistic user flows: file listing, navigation, file creation,
prompt rendering, snapshot consistency, session isolation, and error
recovery. Uses the ``runtime_shell`` fixture (fully initialized shell
with commands loaded) and ``runtime`` fixture for multi-session tests.
"""

from tests.helpers import assert_error
from tests.helpers import assert_not_success
from tests.helpers import assert_success
from tests.helpers import stdout_text


class TestFullShellFlow:
    """End-to-end user workflows: real command sequences.

    Uses the ``runtime_shell`` fixture (fully initialized shell via
    ``SNXRuntime`` with the ``"hello"`` scenario) or the ``runtime``
    fixture for multi-session tests.
    """

    def test_start_session_and_list_files(self, runtime_shell):
        """List files in a directory using the full command path."""
        result = runtime_shell.execute("ls /home/user")
        assert_success(result)
        assert "notes.txt" in stdout_text(result)

    def test_read_file_after_cd(self, runtime_shell):
        """``cd`` into a directory then ``cat`` a file in it (relative path)."""
        runtime_shell.execute("cd /home/user")
        result = runtime_shell.execute("cat notes.txt")
        assert_success(result)
        assert "TO DO" in stdout_text(result)

    def test_create_file_then_read_it(self, runtime_shell):
        """``touch`` a file then verify it appears in ``ls`` output."""
        runtime_shell.execute("touch /home/user/created.txt")
        result = runtime_shell.execute("ls /home/user")
        assert "created.txt" in stdout_text(result)

    def test_navigate_and_prompt_reflects_cwd(self, runtime_shell):
        """Prompt tilde abbreviation updates on ``cd`` between home and non-home dirs."""
        prompt1 = runtime_shell.render_prompt()
        assert "~" in prompt1
        runtime_shell.execute("cd /etc")
        prompt2 = runtime_shell.render_prompt()
        assert "/etc" in prompt2
        assert "~" not in prompt2

    def test_multiple_commands_sequence(self, runtime_shell):
        """A sequence of commands (``pwd``, ``cd``, ``ls``, ``cd ~``) produces correct state."""
        results = []
        for cmd in ["pwd", "cd /", "pwd", "ls", "cd ~", "pwd"]:
            results.append(runtime_shell.execute(cmd))
        assert results[0].stdout == ["/home/user"]
        assert results[2].stdout == ["/"]
        assert results[5].stdout == ["/home/user"]

    def test_session_state_persistence(self, runtime):
        """Session state (CWD, filesystem) persists across multiple commands and retrievals."""
        shell = runtime.create_session(scenario_name="hello", session_id="e2e-7")
        shell.execute("cd /var/log")
        shell.execute("touch test.log")
        shell.execute("cd /")

        s = runtime.get_session("e2e-7")
        assert s.session.current_directory == "/"
        assert s.filesystem.exists("/var/log/test.log")

    def test_snapshot_consistency_after_mutations(self, runtime):
        """Snapshot reflects all state changes (CWD, new files, session ID, scenario name)."""
        shell = runtime.create_session(scenario_name="hello", session_id="e2e-snap")
        shell.execute("cd /etc")
        shell.execute("touch /etc/new.conf")
        shell.execute("cd /")

        snap = shell.get_snapshot()
        assert snap.current_path == "/"
        assert "/etc/new.conf" in snap.filesystem
        assert snap.session_id == "e2e-snap"
        assert snap.scenario_name == "Hello SIMNUX"

    def test_filesystem_mutations_visible_in_snapshot(self, runtime_shell):
        """New files created via ``touch`` appear in the shell snapshot."""
        runtime_shell.execute("touch /tmp/testfile")
        snapshot = runtime_shell.get_snapshot()
        assert "/tmp/testfile" in snapshot.filesystem

    def test_prompt_cwd_coherence(self, runtime_shell):
        """Prompt tilde and path always stay in sync with the session's CWD."""
        runtime_shell.execute("cd /home/user")
        assert "~" in runtime_shell.render_prompt()
        runtime_shell.execute("cd /")
        assert "~" not in runtime_shell.render_prompt()
        assert "/" in runtime_shell.render_prompt()

    def test_echo_and_ls_commands(self, runtime_shell):
        """``echo`` and ``ls`` work independently and produce correct output."""
        content = runtime_shell.execute("echo 'hello world'").stdout
        assert "hello world" in " ".join(content)
        ls_result = runtime_shell.execute("ls /home/user")
        assert "notes.txt" in " ".join(ls_result.stdout)

    def test_sessions_are_isolated(self, runtime):
        """Separate sessions have independent filesystems (no cross-session leakage)."""
        shell_a = runtime.create_session(scenario_name="hello", session_id="session-a")
        shell_b = runtime.create_session(scenario_name="hello", session_id="session-b")

        shell_a.execute("touch /home/user/a.txt")

        assert shell_a.filesystem.exists("/home/user/a.txt")
        assert not shell_b.filesystem.exists("/home/user/a.txt")

    def test_failed_command_does_not_corrupt_shell_state(self, runtime_shell):
        """A failing command (``cat`` on nonexistent file) leaves CWD and prompt intact."""
        runtime_shell.execute("cd /etc")

        result = runtime_shell.execute("cat nonexistent-file")

        assert_not_success(result)

        assert runtime_shell.session.current_directory == "/etc"
        assert "/etc" in runtime_shell.render_prompt()


class TestShellEdgeCases:
    """Edge-case command behaviors: empty input, quoted spaces, recovery after error."""

    def test_empty_command_is_noop(self, runtime_shell):
        """An empty command returns success with empty stdout (no crash)."""
        result = runtime_shell.execute("")
        assert_success(result)
        assert result.stdout == []

    def test_quoted_arguments_preserve_spacing(self, runtime_shell):
        """Double-quoted arguments preserve interior spacing."""
        result = runtime_shell.execute('echo "hello   world"')
        assert "hello   world" in " ".join(result.stdout)

    def test_unknown_then_valid(self, runtime_shell):
        """Shell recovers gracefully: an unknown command does not prevent subsequent valid commands."""
        r1 = runtime_shell.execute("nonexistent")
        assert_error(r1)
        r2 = runtime_shell.execute("echo back-on-track")
        assert_success(r2)
