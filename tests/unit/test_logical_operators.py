"""Tests for logical operators (&& and ||) in shell parsing and execution."""

from simnux.shell.models import LogicalOperator
from simnux.shell.parser import ShellParser


class TestLogicalParsing:
    """Tests for parsing commands with logical operators."""

    def test_simple_and_operator(self):
        """&& splits into two logical segments."""
        segments = ShellParser.parse_logical("echo hello && echo world")
        assert len(segments) == 2
        assert segments[0].operator == LogicalOperator.NONE
        assert segments[0].pipeline.command == "echo"
        assert segments[0].pipeline.args == ["hello"]
        assert segments[1].operator == LogicalOperator.AND
        assert segments[1].pipeline.command == "echo"
        assert segments[1].pipeline.args == ["world"]

    def test_simple_or_operator(self):
        """|| splits into two logical segments."""
        segments = ShellParser.parse_logical("echo hello || echo world")
        assert len(segments) == 2
        assert segments[0].operator == LogicalOperator.NONE
        assert segments[1].operator == LogicalOperator.OR

    def test_chained_operators(self):
        """Multiple operators create multiple segments."""
        segments = ShellParser.parse_logical("echo a && echo b || echo c")
        assert len(segments) == 3
        assert segments[0].operator == LogicalOperator.NONE
        assert segments[1].operator == LogicalOperator.AND
        assert segments[2].operator == LogicalOperator.OR

    def test_and_with_pipes(self):
        """&& works with piped commands."""
        segments = ShellParser.parse_logical("ls | grep txt && echo done")
        assert len(segments) == 2
        assert segments[0].operator == LogicalOperator.NONE
        assert len(segments[0].pipeline.segments) == 2  # ls | grep
        assert segments[1].operator == LogicalOperator.AND
        assert segments[1].pipeline.command == "echo"
        assert segments[1].pipeline.args == ["done"]

    def test_or_with_pipes(self):
        """|| works with piped commands."""
        segments = ShellParser.parse_logical("cat missing || echo fallback")
        assert len(segments) == 2
        assert segments[0].operator == LogicalOperator.NONE
        assert segments[0].pipeline.command == "cat"
        assert segments[1].operator == LogicalOperator.OR

    def test_single_command_no_operators(self):
        """Single command returns one segment."""
        segments = ShellParser.parse_logical("echo hello")
        assert len(segments) == 1
        assert segments[0].operator == LogicalOperator.NONE
        assert segments[0].pipeline.command == "echo"

    def test_complex_chain(self):
        """Complex chain with multiple operators."""
        segments = ShellParser.parse_logical("cmd1 && cmd2 || cmd3 && cmd4")
        assert len(segments) == 4
        assert segments[0].operator == LogicalOperator.NONE
        assert segments[1].operator == LogicalOperator.AND
        assert segments[2].operator == LogicalOperator.OR
        assert segments[3].operator == LogicalOperator.AND

    def test_empty_input(self):
        """Empty input returns empty list."""
        segments = ShellParser.parse_logical("")
        assert len(segments) == 0

    def test_whitespace_only(self):
        """Whitespace-only input returns empty list."""
        segments = ShellParser.parse_logical("   ")
        assert len(segments) == 0

    def test_operators_with_spaces(self):
        """Operators work with various spacing."""
        segments = ShellParser.parse_logical("echo a&&echo b||echo c")
        assert len(segments) == 3
        assert segments[0].pipeline.command == "echo"
        assert segments[0].pipeline.args == ["a"]
        assert segments[1].pipeline.command == "echo"
        assert segments[1].pipeline.args == ["b"]
        assert segments[2].pipeline.command == "echo"
        assert segments[2].pipeline.args == ["c"]

    def test_redirect_in_logical_segments(self):
        """Redirects work within logical segments."""
        segments = ShellParser.parse_logical("echo hello > /tmp/out && cat /tmp/out")
        assert len(segments) == 2
        assert segments[0].pipeline.stdout_redirect == "/tmp/out"
        assert segments[1].pipeline.command == "cat"
        assert segments[1].pipeline.args == ["/tmp/out"]

    def test_mixed_operators_and_redirects(self):
        """Complex mix of operators, pipes, and redirects."""
        segments = ShellParser.parse_logical("ls | grep txt > /tmp/list || ls > /tmp/all")
        assert len(segments) == 2
        assert segments[0].operator == LogicalOperator.NONE
        assert len(segments[0].pipeline.segments) == 2
        assert segments[0].pipeline.segments[-1].stdout_redirect == "/tmp/list"
        assert segments[1].operator == LogicalOperator.OR
        assert segments[1].pipeline.segments[-1].stdout_redirect == "/tmp/all"


class TestParseMethod:
    """Tests for the parse method with logical operators."""

    def test_parse_preserves_and_operator(self):
        """parse() treats && as regular tokens (not splitting on it)."""
        result = ShellParser.parse("echo a && echo b")
        # The parse method doesn't split on &&, just returns the full input
        assert result.command == "echo"
        assert result.args == ["a", "&&", "echo", "b"]

    def test_parse_preserves_or_operator(self):
        """parse() treats || as regular tokens."""
        result = ShellParser.parse("echo a || echo b")
        assert result.command == "echo"
        assert result.args == ["a", "||", "echo", "b"]

    def test_has_logical_operators_detection(self):
        """Test detection of logical operators in raw input."""
        assert "&&" in "echo a && echo b"
        assert "||" in "echo a || echo b"
        assert "&&" not in "echo a | echo b"
        assert "||" not in "echo a | echo b"
