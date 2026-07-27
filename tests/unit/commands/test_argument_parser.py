"""Tests for the declarative argument parser.

Covers short flags, combined short flags, long flags, value-taking
options (attached and separate), the ``--`` end-of-options sentinel,
GNU-format error messages, and the no-op empty case.
"""

from simnux.commands.argument_parser import parse_arguments


BOOL_SPEC = {
    "long": {"flags": ["-l"], "type": bool, "help": "long format"},
    "all": {"flags": ["-a", "--all"], "type": bool, "help": "show all"},
    "verbose": {"flags": ["-v", "--verbose"], "type": bool, "help": "verbose"},
}

VALUE_SPEC = {
    "lines": {"flags": ["-n", "--lines"], "type": str, "help": "number of lines"},
    "output": {"flags": ["-o", "--output"], "type": str, "help": "output file"},
}

MIXED_SPEC = {**BOOL_SPEC, **VALUE_SPEC}


class TestShortFlags:
    """Single-character short flags (``-v``, ``-l``, ``-a``)."""

    def test_single_short_flag(self):
        parsed, errors = parse_arguments(["-v"], BOOL_SPEC, "test")
        assert errors == []
        assert parsed.flags == {"verbose": True}
        assert parsed.positional == []

    def test_multiple_short_flags(self):
        parsed, errors = parse_arguments(["-v", "-l", "-a"], BOOL_SPEC, "test")
        assert errors == []
        assert parsed.flags == {"verbose": True, "long": True, "all": True}
        assert parsed.positional == []

    def test_combined_short_flags(self):
        parsed, errors = parse_arguments(["-vla"], BOOL_SPEC, "test")
        assert errors == []
        assert parsed.flags == {"verbose": True, "long": True, "all": True}
        assert parsed.positional == []

    def test_unknown_short_flag(self):
        parsed, errors = parse_arguments(["-x"], BOOL_SPEC, "test")
        assert errors == ["test: invalid option -- 'x'"]
        assert parsed.flags == {}

    def test_unknown_flag_in_combined(self):
        parsed, errors = parse_arguments(["-vx"], BOOL_SPEC, "test")
        assert errors == ["test: invalid option -- 'x'"]
        assert parsed.flags == {"verbose": True}

    def test_flags_with_positional(self):
        parsed, errors = parse_arguments(["-v", "file.txt"], BOOL_SPEC, "test")
        assert errors == []
        assert parsed.flags == {"verbose": True}
        assert parsed.positional == ["file.txt"]


class TestLongFlags:
    """Long flags (``--all``, ``--verbose``)."""

    def test_long_flag(self):
        parsed, errors = parse_arguments(["--all"], BOOL_SPEC, "test")
        assert errors == []
        assert parsed.flags == {"all": True}
        assert parsed.positional == []

    def test_multiple_long_flags(self):
        parsed, errors = parse_arguments(["--all", "--verbose"], BOOL_SPEC, "test")
        assert errors == []
        assert parsed.flags == {"all": True, "verbose": True}

    def test_unknown_long_flag(self):
        parsed, errors = parse_arguments(["--unknown"], BOOL_SPEC, "test")
        assert errors == ["test: unrecognized option '--unknown'"]
        assert parsed.flags == {}


class TestValueOptions:
    """Value-taking options (``-n 5``, ``--lines=10``)."""

    def test_short_with_separate_value(self):
        parsed, errors = parse_arguments(["-n", "5"], VALUE_SPEC, "test")
        assert errors == []
        assert parsed.flags == {"lines": "5"}
        assert parsed.positional == []

    def test_short_with_attached_value(self):
        parsed, errors = parse_arguments(["-n5"], VALUE_SPEC, "test")
        assert errors == []
        assert parsed.flags == {"lines": "5"}

    def test_long_with_separate_value(self):
        parsed, errors = parse_arguments(["--lines", "10"], VALUE_SPEC, "test")
        assert errors == []
        assert parsed.flags == {"lines": "10"}

    def test_long_with_attached_value(self):
        parsed, errors = parse_arguments(["--lines=10"], VALUE_SPEC, "test")
        assert errors == []
        assert parsed.flags == {"lines": "10"}

    def test_missing_value_for_short(self):
        parsed, errors = parse_arguments(["-n"], VALUE_SPEC, "test")
        assert errors == ["test: option requires an argument -- 'n'"]

    def test_missing_value_for_long(self):
        parsed, errors = parse_arguments(["--lines"], VALUE_SPEC, "test")
        assert errors == ["test: option '--lines' requires an argument"]


class TestEndOfOptions:
    """The ``--`` sentinel forces remaining arguments into positional."""

    def test_double_dash_halts_flag_parsing(self):
        parsed, errors = parse_arguments(["-v", "--", "-a", "file"], BOOL_SPEC, "test")
        assert errors == []
        assert parsed.flags == {"verbose": True}
        assert parsed.positional == ["-a", "file"]

    def test_double_dash_with_no_flags_before(self):
        parsed, errors = parse_arguments(["--", "file.txt"], BOOL_SPEC, "test")
        assert errors == []
        assert parsed.flags == {}
        assert parsed.positional == ["file.txt"]

    def test_double_dash_alone(self):
        parsed, errors = parse_arguments(["--"], BOOL_SPEC, "test")
        assert errors == []
        assert parsed.flags == {}
        assert parsed.positional == []


class TestEdgeCases:
    """Empty input, None args, no spec."""

    def test_none_args(self):
        parsed, errors = parse_arguments(None, BOOL_SPEC, "test")
        assert errors == []
        assert parsed.flags == {}
        assert parsed.positional == []

    def test_empty_list(self):
        parsed, errors = parse_arguments([], BOOL_SPEC, "test")
        assert errors == []
        assert parsed.flags == {}
        assert parsed.positional == []

    def test_empty_spec(self):
        parsed, errors = parse_arguments(["-v", "file"], {}, "test")
        assert errors == ["test: invalid option -- 'v'"]
        assert parsed.flags == {}
        assert parsed.positional == ["file"]


class TestMixedUsage:
    """Realistic combinations of flags, options, and positional args."""

    def test_flags_and_value_and_positional(self):
        parsed, errors = parse_arguments(["-v", "-n", "5", "file.txt"], MIXED_SPEC, "test")
        assert errors == []
        assert parsed.flags == {"verbose": True, "lines": "5"}
        assert parsed.positional == ["file.txt"]

    def test_combined_and_value_and_positional(self):
        parsed, errors = parse_arguments(["-vn5", "file.txt"], MIXED_SPEC, "test")
        assert errors == []
        assert parsed.flags == {"verbose": True, "lines": "5"}
        assert parsed.positional == ["file.txt"]

    def test_long_flags_and_positional(self):
        parsed, errors = parse_arguments(
            ["--verbose", "--lines=10", "file.txt"], MIXED_SPEC, "test"
        )
        assert errors == []
        assert parsed.flags == {"verbose": True, "lines": "10"}
        assert parsed.positional == ["file.txt"]

    def test_trailing_value_after_value_flag(self):
        """-o value must not consume a subsequent flag as value."""
        parsed, errors = parse_arguments(["-o", "out.log", "-v"], MIXED_SPEC, "test")
        assert errors == []
        assert parsed.flags == {"output": "out.log", "verbose": True}
        assert parsed.positional == []


class TestGnuErrorFormatting:
    """Error messages match GNU coreutils conventions."""

    def test_invalid_short_option(self):
        _, errors = parse_arguments(["-x"], BOOL_SPEC, "ls")
        assert errors == ["ls: invalid option -- 'x'"]

    def test_invalid_short_option_in_chain(self):
        _, errors = parse_arguments(["-vx"], BOOL_SPEC, "ls")
        assert errors == ["ls: invalid option -- 'x'"]

    def test_unrecognized_long_option(self):
        _, errors = parse_arguments(["--foobar"], BOOL_SPEC, "grep")
        assert errors == ["grep: unrecognized option '--foobar'"]

    def test_option_requires_argument_short(self):
        _, errors = parse_arguments(["-n"], VALUE_SPEC, "head")
        assert errors == ["head: option requires an argument -- 'n'"]

    def test_option_requires_argument_long(self):
        _, errors = parse_arguments(["--lines"], VALUE_SPEC, "wc")
        assert errors == ["wc: option '--lines' requires an argument"]


class TestCommandNameInErrors:
    """The command name is correctly propagated into error messages."""

    def test_command_name_appears(self):
        _, errors = parse_arguments(["-x"], BOOL_SPEC, "mycommand")
        assert errors[0].startswith("mycommand:")
