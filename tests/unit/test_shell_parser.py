"""Tests for ShellParser — POSIX-style shell input tokenization.

Covers empty/whitespace input, simple commands, quoted strings,
escape sequences, tab separation, and error cases (unclosed quotes,
trailing backslash).
"""

import pytest

from simnux.shell.parser import ShellParser


class TestShellParser:
    """Shell input tokenization: command + args extraction via shlex.

    Validates POSIX-compatible quoting, escaping, whitespace handling,
    and error detection for malformed input.
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
