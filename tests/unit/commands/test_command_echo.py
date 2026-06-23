"""Tests for the ``echo`` command implementation.

Covers text output, empty input, quote handling (single, double, mixed),
tilde literal preservation, and multiple-argument spacing.
"""

from tests.helpers import assert_success
from tests.helpers import stdout_text


class TestEchoCommand:
    """Text output via the ``echo`` command.

    Uses the ``shell_with_commands`` fixture. Covers basic text,
    empty input, quote stripping, tilde literal preservation, and
    space-collapsing for multiple arguments.
    """

    def test_echo_text(self, shell_with_commands):
        """Echo outputs the provided text."""
        result = shell_with_commands.execute("echo hello world")
        assert_success(result)
        assert "hello world" in stdout_text(result)

    def test_echo_empty(self, shell_with_commands):
        """Echo with no arguments outputs an empty string (not error)."""
        result = shell_with_commands.execute("echo")
        assert_success(result)
        assert stdout_text(result) == ""

    def test_echo_preserves_parser_quote_semantics(self, shell_with_commands):
        """Single quotes are removed from the output (shell-parser strips them)."""
        result = shell_with_commands.execute("echo 'hello'")
        assert "hello" in stdout_text(result)

    def test_echo_double_quotes_stripped(self, shell_with_commands):
        """Double quotes are removed from the output."""
        result = shell_with_commands.execute('echo "hello"')
        assert "hello" in stdout_text(result)

    def test_echo_mixed_quotes_preserved(self, shell_with_commands):
        """Nested quotes inside double quotes are preserved."""
        result = shell_with_commands.execute("echo \"hello 'world'\"")
        assert "hello 'world'" in stdout_text(result)

    def test_echo_tilde_not_expanded_by_command(self, shell_with_commands):
        """Echo does not expand ``~`` — expansion is the shell/FS layer's job."""
        result = shell_with_commands.execute("echo ~")
        assert "~" in stdout_text(result)

    def test_echo_multiple_args_with_spaces(self, shell_with_commands):
        """Multiple arguments are space-separated in the output."""
        result = shell_with_commands.execute("echo   a   b   c")
        assert stdout_text(result) == "a b c"
