"""Tests for ShellParser — POSIX-style shell input tokenization.

Covers empty/whitespace input, simple commands, quoted strings, escape
sequences, tab separation, and error cases (unclosed quotes, trailing
backslash).
"""

import pytest

from simnux.core.shell.parser import ShellParser


class TestShellParser:
    """Shell input tokenization: command + args extraction via shlex.

    Validates POSIX-compatible quoting, escaping, whitespace handling, and error
    detection for malformed input.
    """

    def test_empty_input(self):
        """Empty string returns empty command and no args."""
        result = ShellParser.parse("")
        assert result.command == ""
        assert result.args == []

    def test_only_whitespace(self):
        """Whitespace-only input returns empty command (treated as blank)."""
        result = ShellParser.parse("   ")
        assert result.command == ""
        assert result.args == []

    def test_simple_command(self):
        """A command with no arguments is parsed correctly."""
        result = ShellParser.parse("ls")
        assert result.command == "ls"
        assert result.args == []

    def test_command_with_args(self):
        """Command and arguments are split correctly."""
        result = ShellParser.parse("ls -la /home")
        assert result.command == "ls"
        assert result.args == ["-la", "/home"]

    def test_multiple_spaces_collapsed(self):
        """Multiple consecutive spaces are treated as a single separator."""
        result = ShellParser.parse("echo   hello    world")
        assert result.command == "echo"
        assert result.args == ["hello", "world"]

    def test_single_quoted_string(self):
        """Single-quoted strings preserve interior spaces as a single argument."""
        result = ShellParser.parse("echo 'hello world'")
        assert result.command == "echo"
        assert result.args == ["hello world"]

    def test_double_quoted_string(self):
        """Double-quoted strings preserve interior spaces as a single argument."""
        result = ShellParser.parse('echo "hello world"')
        assert result.command == "echo"
        assert result.args == ["hello world"]

    def test_mixed_quoting(self):
        """Nested single quotes inside double quotes are preserved."""
        result = ShellParser.parse("echo \"hello 'nested' world\"")
        assert result.command == "echo"
        assert result.args == ["hello 'nested' world"]

    def test_escaped_characters(self):
        """Backslash-escaped spaces are preserved as part of the argument."""
        result = ShellParser.parse("echo hello\\ world")
        assert result.command == "echo"
        assert result.args == ["hello world"]

    def test_escaped_quote(self):
        """Backslash-escaped quotes are literal characters in the argument."""
        result = ShellParser.parse("echo hello\\'world")
        assert result.command == "echo"
        assert result.args == ["hello'world"]

    def test_backslash_escaping(self):
        """Backslash preserves special characters like ``$`` literally."""
        result = ShellParser.parse("echo \\$HOME")
        assert result.command == "echo"
        assert result.args == ["$HOME"]

    def test_consecutive_escaped_spaces(self):
        """Consecutive escaped spaces produce multiple spaces in the argument."""
        result = ShellParser.parse("echo a\\ \\ b")
        assert result.command == "echo"
        assert result.args == ["a  b"]

    def test_tab_separated_args(self):
        """Tabs are valid argument separators (whitespace)."""
        result = ShellParser.parse("echo\tfoo\tbar")
        assert result.command == "echo"
        assert result.args == ["foo", "bar"]

    def test_newline_inside_quotes(self):
        """Newlines inside quoted strings are preserved as literal characters."""
        result = ShellParser.parse("echo 'line1\nline2'")
        assert result.command == "echo"
        assert result.args == ["line1\nline2"]

    def test_unclosed_single_quote_raises(self):
        """Unclosed single quotes raise ``ValueError`` (prevents ambiguous parsing)."""
        with pytest.raises(ValueError):
            ShellParser.parse("echo 'unclosed")

    def test_unclosed_double_quote_raises(self):
        """Unclosed double quotes raise ``ValueError``."""
        with pytest.raises(ValueError):
            ShellParser.parse('echo "unclosed')

    def test_argument_with_only_quotes(self):
        """Empty single quotes produce an empty-string argument."""
        result = ShellParser.parse("echo ''")
        assert result.args == [""]

    def test_empty_double_quotes(self):
        """Empty double quotes produce an empty-string argument."""
        result = ShellParser.parse('echo ""')
        assert result.args == [""]

    def test_multiple_arguments_quoted_and_unquoted(self):
        """Mixed quoted and unquoted arguments are all parsed correctly."""
        result = ShellParser.parse('cmd arg1 "arg two" arg3')
        assert result.command == "cmd"
        assert result.args == ["arg1", "arg two", "arg3"]

    def test_very_long_input(self):
        """Parser handles long input with 100 arguments without issue."""
        long = "echo " + " ".join(f"arg{i}" for i in range(100))
        result = ShellParser.parse(long)
        assert result.command == "echo"
        assert len(result.args) == 100

    def test_command_with_hyphen_and_equals(self):
        """Arguments with ``--option=value`` syntax are not split on ``=``."""
        result = ShellParser.parse("cmd --option=value")
        assert result.args == ["--option=value"]

    def test_path_arguments(self):
        """Absolute paths are parsed as single arguments."""
        result = ShellParser.parse("cat /etc/hostname")
        assert result.args == ["/etc/hostname"]

    def test_tilde_path_argument(self):
        """Tilde paths are preserved literally (expansion is not the parser's job)."""
        result = ShellParser.parse("echo ~/docs/file.txt")
        assert result.args == ["~/docs/file.txt"]

    def test_invalid_quote_after_backslash(self):
        """A backslash before a closing quote inside a single-quoted string is invalid."""
        with pytest.raises(ValueError):
            ShellParser.parse("echo '\\")

    def test_single_backslash_at_end(self):
        """Trailing backslash (incomplete escape) raises ``ValueError``."""
        with pytest.raises(ValueError):
            ShellParser.parse("echo hello\\")

    # ── stdout redirection (>, >>) ────────────────────────────────────────────

    def test_redirect_stdout_to_file(self):
        """``>`` operator redirects stdout to a file."""
        result = ShellParser.parse("echo hello > out.txt")
        assert result.command == "echo"
        assert result.args == ["hello"]
        assert result.stdout_redirect == "out.txt"
        assert result.stdout_append is False

    def test_redirect_append_to_file(self):
        """``>>`` operator appends stdout to a file."""
        result = ShellParser.parse("echo hello >> out.txt")
        assert result.command == "echo"
        assert result.args == ["hello"]
        assert result.stdout_redirect == "out.txt"
        assert result.stdout_append is True

    def test_redirect_no_args(self):
        """Redirect works even when the command has no arguments."""
        result = ShellParser.parse("ls > listing.txt")
        assert result.command == "ls"
        assert result.args == []
        assert result.stdout_redirect == "listing.txt"

    def test_redirect_before_command(self):
        """Redirect operator can appear before the command name."""
        result = ShellParser.parse("> out.txt echo hello")
        assert result.command == "echo"
        assert result.args == ["hello"]
        assert result.stdout_redirect == "out.txt"

    def test_redirect_middle_of_args(self):
        """Redirect operator can appear between arguments."""
        result = ShellParser.parse("echo hello > out.txt world")
        assert result.command == "echo"
        assert result.args == ["hello", "world"]
        assert result.stdout_redirect == "out.txt"

    def test_redirect_multiple_last_wins(self):
        """When multiple redirects are present, the last one wins."""
        result = ShellParser.parse("echo hello > first.txt > last.txt")
        assert result.command == "echo"
        assert result.args == ["hello"]
        assert result.stdout_redirect == "last.txt"

    def test_redirect_missing_target_raises(self):
        """``>`` without a target file raises ValueError."""
        with pytest.raises(ValueError, match="Missing redirect target"):
            ShellParser.parse("echo hello >")

    def test_redirect_append_missing_target_raises(self):
        """``>>`` without a target file raises ValueError."""
        with pytest.raises(ValueError, match="Missing redirect target"):
            ShellParser.parse("echo hello >>")

    def test_redirect_only_operator_and_target(self):
        """A command consisting only of a redirect (no real command) returns empty command."""
        result = ShellParser.parse("> out.txt")
        assert result.command == ""
        assert result.args == []
        assert result.stdout_redirect == "out.txt"

    # ── pipeline (|) ──────────────────────────────────────────────────────────

    def test_pipe_two_commands(self):
        """Basic pipe between two commands."""
        result = ShellParser.parse("ls | grep notes")
        assert len(result.segments) == 2

        assert result.segments[0].command == "ls"
        assert result.segments[0].args == []

        assert result.segments[1].command == "grep"
        assert result.segments[1].args == ["notes"]

    def test_pipe_three_commands(self):
        """Three-stage pipeline."""
        result = ShellParser.parse("cat file | grep pattern | wc -l")
        assert len(result.segments) == 3

        assert result.segments[0].command == "cat"
        assert result.segments[0].args == ["file"]

        assert result.segments[1].command == "grep"
        assert result.segments[1].args == ["pattern"]

        assert result.segments[2].command == "wc"
        assert result.segments[2].args == ["-l"]

    def test_pipe_with_args(self):
        """Pipe with arguments on both sides."""
        result = ShellParser.parse("ls -la /home | grep user")
        assert result.segments[0].args == ["-la", "/home"]
        assert result.segments[1].args == ["user"]

    def test_pipe_backward_compat_first_segment(self):
        """Backward-compat properties (command, args) reflect first segment."""
        result = ShellParser.parse("ls -la | grep foo")
        assert result.command == "ls"
        assert result.args == ["-la"]

    def test_pipe_stdout_redirect_on_last(self):
        """Redirect on the final pipeline segment is extracted correctly."""
        result = ShellParser.parse("ls | grep notes > output.txt")
        assert len(result.segments) == 2
        assert result.segments[1].stdout_redirect == "output.txt"
        assert result.segments[1].stdout_append is False

    def test_pipe_no_spaces_around_operator(self):
        """Pipe works without spaces around ``|`` (pre-processing adds them)."""
        result = ShellParser.parse("ls|grep notes")
        assert len(result.segments) == 2
        assert result.segments[0].command == "ls"
        assert result.segments[1].command == "grep"
        assert result.segments[1].args == ["notes"]

    def test_pipe_trailing_pipe_raises(self):
        """Trailing ``|`` raises ValueError (empty segment)."""
        with pytest.raises(ValueError, match="Empty pipeline segment"):
            ShellParser.parse("ls | grep |")

    def test_pipe_leading_pipe_raises(self):
        """Leading ``|`` raises ValueError (empty segment)."""
        with pytest.raises(ValueError, match="Empty pipeline segment"):
            ShellParser.parse("| ls")

    def test_pipe_empty_segment_raises(self):
        """Consecutive ``|`` with nothing in between raises ValueError."""
        with pytest.raises(ValueError, match="Empty pipeline segment"):
            ShellParser.parse("ls | | grep")
