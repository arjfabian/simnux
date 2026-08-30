"""Tests for POSIX history expansion engine."""

import pytest

from simnux.core.scripting.history import CommandHistory


class TestHistoryBangBang:
    """!! expands to the most recent command."""

    def test_bang_bang_repeats_previous(self):
        h = CommandHistory(["echo hello", "ls -la"])
        result, expanded = h.expand("!!")
        assert result == "ls -la"
        assert expanded is True

    def test_bang_bang_empty_history_raises(self):
        h = CommandHistory([])
        with pytest.raises(ValueError, match="event not found"):
            h.expand("!!")

    def test_bang_bang_in_prefix(self):
        h = CommandHistory(["echo hello"])
        result, expanded = h.expand("!! world")
        assert result == "echo hello world"
        assert expanded is True

    def test_bang_bang_in_suffix(self):
        h = CommandHistory(["echo hello"])
        result, expanded = h.expand("echo !!")
        assert result == "echo echo hello"
        assert expanded is True


class TestHistoryBangN:
    """!n expands to 1-indexed history number."""

    def test_bang_1_returns_first(self):
        h = CommandHistory(["echo first", "echo second", "echo third"])
        result, expanded = h.expand("!1")
        assert result == "echo first"
        assert expanded is True

    def test_bang_2_returns_second(self):
        h = CommandHistory(["echo first", "echo second"])
        result, expanded = h.expand("!2")
        assert result == "echo second"
        assert expanded is True

    def test_bang_0_raises(self):
        h = CommandHistory(["echo first"])
        with pytest.raises(ValueError, match="event not found"):
            h.expand("!0")

    def test_bang_out_of_range_raises(self):
        h = CommandHistory(["echo first"])
        with pytest.raises(ValueError, match="event not found"):
            h.expand("!5")


class TestHistoryBangMinusN:
    """!-n expands to relative past command (n lines back)."""

    def test_bang_minus_1_returns_previous(self):
        h = CommandHistory(["echo first", "echo second"])
        result, expanded = h.expand("!-1")
        assert result == "echo second"
        assert expanded is True

    def test_bang_minus_2_returns_two_back(self):
        h = CommandHistory(["echo a", "echo b", "echo c"])
        result, expanded = h.expand("!-2")
        assert result == "echo b"
        assert expanded is True

    def test_bang_minus_too_far_raises(self):
        h = CommandHistory(["echo a"])
        with pytest.raises(ValueError, match="event not found"):
            h.expand("!-2")

    def test_bang_minus_0_raises(self):
        h = CommandHistory(["echo a"])
        with pytest.raises(ValueError, match="event not found"):
            h.expand("!-0")


class TestHistoryBangString:
    """!string expands to most recent command starting with string."""

    def test_bang_prefix_matches(self):
        h = CommandHistory(["echo hello", "echo world", "ls -la"])
        result, expanded = h.expand("!ec")
        assert result == "echo world"
        assert expanded is True

    def test_bang_prefix_finds_most_recent(self):
        h = CommandHistory(["echo first", "ls", "echo second"])
        result, expanded = h.expand("!ec")
        assert result == "echo second"
        assert expanded is True

    def test_bang_prefix_no_match_raises(self):
        h = CommandHistory(["echo hello", "ls -la"])
        with pytest.raises(ValueError, match="event not found"):
            h.expand("!xyz")

    def test_bang_numeric_with_suffix(self):
        """!123abc is treated as !123 (numeric) with abc as literal suffix."""
        h = CommandHistory(["echo hello", "echo world"])
        with pytest.raises(ValueError, match="event not found"):
            h.expand("!123abc")


class TestHistoryNoExpansion:
    """Commands without history tokens pass through unchanged."""

    def test_no_bang_returns_unchanged(self):
        h = CommandHistory(["echo hello"])
        result, expanded = h.expand("ls -la")
        assert result == "ls -la"
        assert expanded is False

    def test_empty_string_returns_unchanged(self):
        h = CommandHistory(["echo hello"])
        result, expanded = h.expand("")
        assert result == ""
        assert expanded is False

    def test_none_returns_unchanged(self):
        h = CommandHistory(["echo hello"])
        result, expanded = h.expand(None)
        assert result is None
        assert expanded is False


class TestHistoryMultiExpansion:
    """Multiple history tokens in a single command line."""

    def test_two_bang_bang(self):
        h = CommandHistory(["echo hello", "ls -la"])
        result, expanded = h.expand("!! && !!")
        assert result == "ls -la && ls -la"
        assert expanded is True

    def test_bang_bang_and_bang_n(self):
        h = CommandHistory(["echo first", "echo second"])
        result, expanded = h.expand("!! ; !1")
        assert result == "echo second ; echo first"
        assert expanded is True

    def test_bang_prefix_and_bang_bang(self):
        h = CommandHistory(["echo hello", "ls"])
        result, expanded = h.expand("!ec && !!")
        assert result == "echo hello && ls"
        assert expanded is True


class TestHistoryEdgeCases:
    """Edge cases and boundary conditions."""

    def test_bang_at_end_of_command(self):
        h = CommandHistory(["echo hello"])
        result, expanded = h.expand("test !1")
        assert result == "test echo hello"
        assert expanded is True

    def test_bang_not_in_token_position(self):
        """A bare ! not followed by a valid token is left as-is."""
        h = CommandHistory(["echo hello"])
        result, expanded = h.expand("echo !")
        assert result == "echo !"
        assert expanded is False

    def test_history_entries_read_only_view(self):
        h = CommandHistory(["echo a", "echo b"])
        entries = h.entries
        assert entries == ["echo a", "echo b"]
        # Mutating the view should not affect the original
        entries.append("echo c")
        assert len(h.entries) == 2
