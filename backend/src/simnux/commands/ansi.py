"""ANSI SGR escape code utilities."""

from __future__ import annotations


_SGR: dict[str, str] = {
    "reset": "0",
    "bold": "1",
    "dim": "2",
    "italic": "3",
    "underline": "4",
    "reverse": "7",
    "black": "30",
    "red": "31",
    "green": "32",
    "yellow": "33",
    "blue": "34",
    "magenta": "35",
    "cyan": "36",
    "white": "37",
    "bright_black": "90",
    "bright_red": "91",
    "bright_green": "92",
    "bright_yellow": "93",
    "bright_blue": "94",
    "bright_magenta": "95",
    "bright_cyan": "96",
    "bright_white": "97",
}


def _esc(param: str) -> str:
    return f"\x1b[{param}m"


def reset() -> str:
    return _esc("0")


def __getattr__(name: str):
    if name in _SGR:
        def _wrapper(text: str) -> str:
            return f"{_esc(_SGR[name])}{text}{_esc('0')}"
        _wrapper.__name__ = name
        _wrapper.__qualname__ = name
        _wrapper.__module__ = __name__
        return _wrapper
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
