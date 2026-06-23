"""ANSI console formatter for SIMNUX observability logs.

Applies color-coded output per log level for improved CLI readability.
"""

from datetime import datetime
import logging

from .constants import LOG_LEVEL_OK


class ConsoleLogFormatter(logging.Formatter):
    """ANSI color formatter that maps log levels to terminal colors for
    human-friendly console output.

    File logs use plain-text format instead. The ``OK`` custom level (25)
    renders green for quick visual scanning.
    """

    # ANSI colors
    _RESET = "\x1b[0m"
    _GREY = "\x1b[90;20m"
    _WHITE = "\x1b[38;5;250m"
    _BLUE = "\x1b[34m"
    _GREEN = "\x1b[32m"
    _YELLOW = "\x1b[33m"
    _RED = "\x1b[31m"
    _BOLD_RED = "\x1b[31;1m"

    _LEVEL_COLORS: dict[int, str] = {
        logging.DEBUG: _GREY,
        logging.INFO: _WHITE,
        LOG_LEVEL_OK: _GREEN,
        logging.WARNING: _YELLOW,
        logging.ERROR: _RED,
        logging.CRITICAL: _BOLD_RED,
    }

    def format(self, record: logging.LogRecord) -> str:
        """Return a colorized, timestamped log line."""

        timestamp = datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S")

        level_color = self._LEVEL_COLORS.get(record.levelno, self._WHITE)

        entry_ts = f"{self._GREY}{timestamp}{self._RESET}"
        entry_level = f"{level_color}{record.levelname:>7}{self._RESET}"
        entry_src = f"{self._BLUE}[{record.name}]{self._RESET}"
        entry_message = f"{self._WHITE}{record.getMessage()}{self._RESET}"

        return f"{entry_ts} {entry_level} {entry_src} {entry_message}"
