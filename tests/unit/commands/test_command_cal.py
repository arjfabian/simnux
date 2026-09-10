"""Tests for the ``cal`` command implementation.

Covers month display, year display, three-month window, today
highlighting, argument parsing, leap year handling, and error reporting.
"""

from __future__ import annotations

import datetime

import pytest

from simnux.core.commands.standard.cal import _highlight_today
from simnux.core.commands.standard.cal import _month_lines
from simnux.core.commands.standard.cal import _three_month_lines
from simnux.core.commands.standard.cal import _year_lines
from tests.helpers import assert_invalid_args
from tests.helpers import assert_success
from tests.helpers import make_command_shell
from tests.helpers import stderr_text
from tests.helpers import stdout_text


pytestmark = pytest.mark.asyncio


_FIXED_NOW = datetime.datetime(2024, 6, 13, 9, 30, 0)


class TestCalCommand:
    """Calendar display via the ``cal`` command."""

    # -- basic month display ------------------------------------------------

    async def test_cal_specific_month(self, shell_with_commands):
        """``cal 12 2024`` shows December 2024."""
        result = await shell_with_commands.execute("cal 12 2024")
        assert_success(result)
        expected = "\n".join(_month_lines(2024, 12))
        assert stdout_text(result) == expected

    async def test_cal_default(self, base_layer, test_logger):
        """``cal`` with no args shows current month with today highlighted."""
        today = _FIXED_NOW.date()
        shell = make_command_shell(
            base_layer,
            test_logger,
            clock=lambda: _FIXED_NOW,
        )
        result = await shell.execute("cal")
        assert_success(result)
        expected = _highlight_today(_month_lines(today.year, today.month), today)
        assert stdout_text(result) == "\n".join(expected)

    async def test_cal_single_arg_month(self, base_layer, test_logger):
        """``cal 12`` shows December of current year."""
        today = _FIXED_NOW.date()
        shell = make_command_shell(
            base_layer,
            test_logger,
            clock=lambda: _FIXED_NOW,
        )
        result = await shell.execute("cal 12")
        assert_success(result)
        expected = _month_lines(today.year, 12)
        assert stdout_text(result) == "\n".join(expected)

    # -- year display -------------------------------------------------------

    async def test_cal_year(self, shell_with_commands):
        """``cal 2024`` shows all 12 months of 2024."""
        result = await shell_with_commands.execute("cal 2024")
        assert_success(result)
        expected = "\n".join(_year_lines(2024))
        assert stdout_text(result) == expected

    async def test_cal_year_flag(self, base_layer, test_logger):
        """``cal -y`` shows full current year."""
        today = _FIXED_NOW.date()
        shell = make_command_shell(
            base_layer,
            test_logger,
            clock=lambda: _FIXED_NOW,
        )
        result = await shell.execute("cal -y")
        assert_success(result)
        expected = "\n".join(_year_lines(today.year))
        assert stdout_text(result) == expected

    async def test_cal_long_year_flag(self, base_layer, test_logger):
        """``cal --year`` shows full current year."""
        today = _FIXED_NOW.date()
        shell = make_command_shell(
            base_layer,
            test_logger,
            clock=lambda: _FIXED_NOW,
        )
        result = await shell.execute("cal --year")
        assert_success(result)
        expected = "\n".join(_year_lines(today.year))
        assert stdout_text(result) == expected

    # -- three-month display ------------------------------------------------

    async def test_cal_three_flag(self, base_layer, test_logger):
        """``cal -3`` shows three-month window centered on current month."""
        today = _FIXED_NOW.date()
        shell = make_command_shell(
            base_layer,
            test_logger,
            clock=lambda: _FIXED_NOW,
        )
        result = await shell.execute("cal -3")
        assert_success(result)
        expected = "\n".join(_three_month_lines(today.year, today.month))
        assert stdout_text(result) == expected

    async def test_cal_three_with_month_year(self, shell_with_commands):
        """``cal -3 7 2024`` shows three months around July 2024."""
        result = await shell_with_commands.execute("cal -3 7 2024")
        assert_success(result)
        expected = "\n".join(_three_month_lines(2024, 7))
        assert stdout_text(result) == expected

    # -- today highlighting ------------------------------------------------

    async def test_cal_highlights_today_only_in_current_month(self, base_layer, test_logger):
        """Today is highlighted in its own month view and not in another month."""
        today = _FIXED_NOW.date()
        shell = make_command_shell(
            base_layer,
            test_logger,
            clock=lambda: _FIXED_NOW,
        )
        highlighted = _highlight_today(_month_lines(today.year, today.month), today)
        assert highlighted != _month_lines(today.year, today.month)

        result = await shell.execute(f"cal {today.month} {today.year}")
        assert_success(result)
        assert stdout_text(result) == "\n".join(highlighted)

        result = await shell.execute("cal 7 2024")
        assert_success(result)
        expected = "\n".join(_month_lines(2024, 7))
        assert stdout_text(result) == expected

    # -- edge cases ---------------------------------------------------------

    async def test_cal_leap_year(self, shell_with_commands):
        """February 2024 has 29 days (leap year)."""
        result = await shell_with_commands.execute("cal 2 2024")
        assert_success(result)
        output = stdout_text(result)
        assert "29" in output

    async def test_cal_non_leap_year(self, shell_with_commands):
        """February 2023 has 28 days (not a leap year)."""
        result = await shell_with_commands.execute("cal 2 2023")
        assert_success(result)
        output = stdout_text(result)
        assert "28" in output
        assert "29" not in output

    # -- errors -------------------------------------------------------------

    async def test_cal_invalid_month(self, shell_with_commands):
        """``cal 13 2024`` returns INVALID_ARGUMENT."""
        result = await shell_with_commands.execute("cal 13 2024")
        assert_invalid_args(result)
        assert "13 is not a month number" in stderr_text(result)

    async def test_cal_invalid_arg(self, shell_with_commands):
        """``cal abc`` returns INVALID_ARGUMENT."""
        result = await shell_with_commands.execute("cal abc")
        assert_invalid_args(result)
        assert "not a number" in stderr_text(result)

    async def test_cal_too_many_args(self, shell_with_commands):
        """``cal 1 2 3`` returns INVALID_ARGUMENT."""
        result = await shell_with_commands.execute("cal 1 2 3")
        assert_invalid_args(result)
        assert "too many arguments" in stderr_text(result)

    async def test_cal_invalid_month_zero(self, shell_with_commands):
        """``cal 0 2024`` returns INVALID_ARGUMENT for month=0."""
        result = await shell_with_commands.execute("cal 0 2024")
        assert_invalid_args(result)
        assert "is not a month number" in stderr_text(result)
