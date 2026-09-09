"""Tests for the ANSI escape code utilities."""

from __future__ import annotations

from simnux.core.commands import ansi


def _esc(param: str) -> str:
    return f"\x1b[{param}m"


class TestAnsiWrappers:
    """SGR wrapper functions produce correct escape codes."""

    def test_red_wraps_with_31_and_reset(self):
        result = ansi.red("hello")
        assert result == f"{_esc('31')}hello{_esc('0')}"

    def test_green_wraps_with_32_and_reset(self):
        result = ansi.green("hello")
        assert result == f"{_esc('32')}hello{_esc('0')}"

    def test_blue_wraps_with_34_and_reset(self):
        result = ansi.blue("world")
        assert result == f"{_esc('34')}world{_esc('0')}"

    def test_bold_wraps_with_1_and_reset(self):
        result = ansi.bold("hello")
        assert result == f"{_esc('1')}hello{_esc('0')}"

    def test_reverse_wraps_with_7_and_reset(self):
        result = ansi.reverse(" 6 ")
        assert result == f"{_esc('7')} 6 {_esc('0')}"

    def test_underline_wraps_with_4_and_reset(self):
        result = ansi.underline("hello")
        assert result == f"{_esc('4')}hello{_esc('0')}"

    def test_dim_wraps_with_2_and_reset(self):
        result = ansi.dim("hello")
        assert result == f"{_esc('2')}hello{_esc('0')}"

    def test_cyan_wraps_with_36_and_reset(self):
        result = ansi.cyan("link")
        assert result == f"{_esc('36')}link{_esc('0')}"

    def test_yellow_wraps_with_33_and_reset(self):
        result = ansi.yellow("warn")
        assert result == f"{_esc('33')}warn{_esc('0')}"

    def test_magenta_wraps_with_35_and_reset(self):
        result = ansi.magenta("pink")
        assert result == f"{_esc('35')}pink{_esc('0')}"

    def test_white_wraps_with_37_and_reset(self):
        result = ansi.white("light")
        assert result == f"{_esc('37')}light{_esc('0')}"

    def test_black_wraps_with_30_and_reset(self):
        result = ansi.black("dark")
        assert result == f"{_esc('30')}dark{_esc('0')}"

    def test_reset_returns_escape_0(self):
        assert ansi.reset() == _esc("0")

    def test_empty_text_wraps_correctly(self):
        result = ansi.red("")
        assert result == f"{_esc('31')}{_esc('0')}"

    def test_composing_bold_red(self):
        result = ansi.bold(ansi.red("urgent"))
        assert result == f"{_esc('1')}{_esc('31')}urgent{_esc('0')}{_esc('0')}"


class TestAnsiBrightColors:
    """Bright variants map to 90-97 codes."""

    def test_bright_red(self):
        assert ansi.bright_red("x") == f"{_esc('91')}x{_esc('0')}"

    def test_bright_green(self):
        assert ansi.bright_green("x") == f"{_esc('92')}x{_esc('0')}"

    def test_bright_blue(self):
        assert ansi.bright_blue("x") == f"{_esc('94')}x{_esc('0')}"

    def test_bright_cyan(self):
        assert ansi.bright_cyan("x") == f"{_esc('96')}x{_esc('0')}"

    def test_bright_white(self):
        assert ansi.bright_white("x") == f"{_esc('97')}x{_esc('0')}"

    def test_bright_black(self):
        assert ansi.bright_black("x") == f"{_esc('90')}x{_esc('0')}"

    def test_bright_yellow(self):
        assert ansi.bright_yellow("x") == f"{_esc('93')}x{_esc('0')}"

    def test_bright_magenta(self):
        assert ansi.bright_magenta("x") == f"{_esc('95')}x{_esc('0')}"
