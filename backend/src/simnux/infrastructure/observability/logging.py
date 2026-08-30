"""Configure SIMNUX runtime logger with console + file outputs.

Console output is ANSI-colored; file output is plain text for grep
compatibility.
"""

import logging
import sys

from simnux.infrastructure.observability.formatters import ConsoleLogFormatter


def setup_simnux_logger(log_path: str) -> logging.Logger:
    """Get or create the 'simnux' logger with dual output:
    ANSI-colored console (stdout) and plain-text file (log_path).
    Guards against duplicate handlers — idempotent under uvicorn reload.
    """

    logger = logging.getLogger("simnux")
    logger.setLevel(logging.DEBUG)

    # Avoid duplicate handlers in uvicorn reload scenarios
    if logger.handlers:
        return logger

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(ConsoleLogFormatter())

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] [%(name)s] %(message)s")
    )

    logger.addHandler(console)
    logger.addHandler(file_handler)

    return logger
