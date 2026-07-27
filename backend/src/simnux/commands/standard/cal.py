"""cal -- display a calendar."""

from __future__ import annotations

import calendar
import datetime

from simnux.commands import ansi
from simnux.commands.models import CommandContext
from simnux.commands.runtime import SNXCommand
from simnux.commands.streams import AsyncStreamReader
from simnux.commands.streams import AsyncStreamWriter
from simnux.runtime.models import ExitCode


_CAL = calendar.TextCalendar(firstweekday=6)


def _month_lines(year: int, month: int) -> list[str]:
    return _CAL.formatmonth(year, month).splitlines()


def _highlight_today(lines: list[str], year: int, month: int) -> list[str]:
    today = datetime.date.today()
    if today.year != year or today.month != month:
        return lines
    day = today.day
    cell = f" {day} " if day < 10 else f"{day} "
    day_part = cell.rstrip()
    trailing = cell[len(day_part) :]
    highlighted = ansi.reverse(day_part) + trailing
    result = list(lines)
    for i in range(2, len(result)):
        pos = result[i].find(cell)
        if pos != -1:
            result[i] = result[i][:pos] + highlighted + result[i][pos + len(cell) :]
            break
    return result


def _year_lines(year: int) -> list[str]:
    return _CAL.formatyear(year).splitlines()


def _three_month_lines(year: int, month: int) -> list[str]:
    p_year, p_month = (year, month - 1) if month > 1 else (year - 1, 12)
    n_year, n_month = (year, month + 1) if month < 12 else (year + 1, 1)

    left = _month_lines(p_year, p_month)
    center = _month_lines(year, month)
    right = _month_lines(n_year, n_month)

    max_lines = max(len(left), len(center), len(right))

    def _pad(month_lines: list[str]) -> list[str]:
        padded: list[str] = []
        for line in month_lines:
            padded.append(line.ljust(20))
        while len(padded) < max_lines:
            padded.append(" " * 20)
        return padded

    left = _pad(left)
    center = _pad(center)
    right = _pad(right)

    result: list[str] = []
    for i in range(max_lines):
        result.append(f"{left[i]}  {center[i]}  {right[i]}")
    return result


class Command(SNXCommand):
    """Display a calendar."""

    name = "cal"

    parameters = {
        "three": {
            "flags": ["-3"],
            "type": bool,
            "help": "display three months centered on current",
        },
        "year": {"flags": ["-y", "--year"], "type": bool, "help": "display entire current year"},
    }

    async def execute(
        self,
        ctx: CommandContext,
        stdin: AsyncStreamReader,
        stdout: AsyncStreamWriter,
        stderr: AsyncStreamWriter,
    ) -> ExitCode:
        flags = self.parsed_args.flags if self.parsed_args else {}
        pos = self.parsed_args.positional if self.parsed_args else (self.args or [])

        today = datetime.date.today()
        year = today.year
        month = today.month
        show_year = bool(flags.get("year"))

        if len(pos) == 1:
            try:
                val = int(pos[0])
            except ValueError:
                await stderr.write(f"cal: '{pos[0]}' is not a number")
                return ExitCode.INVALID_ARGUMENT
            if 1 <= val <= 12:
                month = val
            else:
                year = val
                show_year = True
        elif len(pos) == 2:
            try:
                m = int(pos[0])
            except ValueError:
                await stderr.write(f"cal: '{pos[0]}' is not a number")
                return ExitCode.INVALID_ARGUMENT
            try:
                y = int(pos[1])
            except ValueError:
                await stderr.write(f"cal: '{pos[1]}' is not a number")
                return ExitCode.INVALID_ARGUMENT
            if not 1 <= m <= 12:
                await stderr.write(f"cal: {m} is not a month number (1..12)")
                return ExitCode.INVALID_ARGUMENT
            month = m
            year = y
        elif len(pos) > 2:
            await stderr.write("cal: too many arguments")
            return ExitCode.INVALID_ARGUMENT

        if show_year:
            lines = _year_lines(year)
        elif flags.get("three"):
            lines = _three_month_lines(year, month)
        else:
            lines = _month_lines(year, month)
            if year == today.year and month == today.month:
                lines = _highlight_today(lines, year, month)

        for line in lines:
            await stdout.write(f"{line}\n")

        return ExitCode.SUCCESS
