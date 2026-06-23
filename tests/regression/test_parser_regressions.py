"""Regression tests for ShellParser edge cases and stability.

Covers unclosed quotes, whitespace-only input, single-character commands,
and whitespace preservation inside quoted strings.
"""

import pytest

from simnux.shell.parser import ShellParser


class TestRegressionShellParserEdgeCases:
    """Parser edge cases: malformed input, whitespace-only, minimal commands."""

    def test_parser_handles_unclosed_quotes_gracefully(self):
        """Unclosed single quotes raise ``ValueError`` instead of hanging."""
        with pytest.raises(ValueError):
            ShellParser.parse("echo 'unclosed")

    def test_parser_empty_after_whitespace(self):
        """Whitespace-only input (including tabs) returns empty command."""
        result = ShellParser.parse("   \t   ")
        assert result.command == ""

    def test_parser_single_char_command(self):
        """A single-character command is parsed as the command with no args."""
        result = ShellParser.parse("x")
        assert result.command == "x"
        assert result.args == []


class TestRegressionShellParserStability:
    """Parser stability: quoted whitespace preservation."""

    def test_parser_preserves_multiple_spaces_inside_quotes(self):
        """Multiple spaces inside double quotes are preserved as a single argument."""
        result = ShellParser.parse('echo "a   b   c"')

        assert result.args == ["a   b   c"]
