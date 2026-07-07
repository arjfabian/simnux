"""Declarative argument parsing with GNU coreutils-style error messages."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field


@dataclass
class ParseResult:
    """Resolved flags and positional arguments."""

    flags: dict[str, bool | str] = field(default_factory=dict)
    positional: list[str] = field(default_factory=list)


def _build_lookup(spec: dict[str, dict]) -> dict[str, str]:
    """Build reverse lookup: command-line flag string → parameter key.

    Example:
        spec = {"all": {"flags": ["-a", "--all"]}}
        → {"-a": "all", "--all": "all"}
    """
    lookup: dict[str, str] = {}
    for key, definition in spec.items():
        for flag_str in definition.get("flags", []):
            lookup[flag_str] = key
    return lookup


def _param_type(key: str, spec: dict[str, dict]) -> type:
    return spec.get(key, {}).get("type", bool)


def parse_arguments(
    raw_args: list[str] | None,
    spec: dict[str, dict],
    command_name: str,
) -> tuple[ParseResult, list[str]]:
    """Parse ``raw_args`` against the declarative parameter ``spec``.

    Parameters
    ----------
    raw_args:
        The raw argument list from the shell parser (may be ``None``).
    spec:
        Parameter definitions. Keys are stable parameter names (short letter
        or long name). Values are dicts with:

        - ``"type"``: ``bool`` (flag, default) or ``str`` (expects value)
        - ``"flags"``: list of command-line forms, e.g. ``["-a", "--all"]``
        - ``"help"``: optional description (reserved for future use)

    command_name:
        Used in error messages (``"cmd: invalid option -- 'x'"``).

    Returns
    -------
    ``(ParseResult, errors)`` where ``errors`` is a list of formatted error
    strings. When ``errors`` is non-empty the caller should reject execution.

    Supported syntax
    ----------------
    - ``-f``          short boolean flag
    - ``-f -g``       multiple short flags
    - ``-fg``         combined short flags (identical to ``-f -g``)
    - ``--flag``      long boolean flag
    - ``-n value``    short option with value
    - ``-nvalue``     short option with attached value
    - ``--name value``  long option with value
    - ``--name=value``  long option with attached value
    - ``--``          end-of-options sentinel (everything after is positional)
    """
    errors: list[str] = []
    result = ParseResult()
    flag_lookup = _build_lookup(spec)

    if not raw_args:
        return result, errors

    args_iter = iter(raw_args)

    for arg in args_iter:
        if arg == "--":
            for remaining in args_iter:
                result.positional.append(remaining)
            break

        if arg.startswith("--"):
            _parse_long(arg, flag_lookup, spec, command_name, args_iter, result, errors)
            continue

        if arg.startswith("-") and len(arg) > 1:
            _parse_short_chain(arg, flag_lookup, spec, command_name, args_iter, result, errors)
            continue

        result.positional.append(arg)

    return result, errors


def _parse_long(
    arg: str,
    flag_lookup: dict[str, str],
    spec: dict[str, dict],
    command_name: str,
    args_iter: iter,
    result: ParseResult,
    errors: list[str],
) -> None:
    """Parse a single long-flag argument (``--flag`` or ``--flag=value``)."""

    if "=" in arg:
        flag_str, value = arg.split("=", 1)
    else:
        flag_str = arg
        value = None

    if flag_str not in flag_lookup:
        errors.append(f"{command_name}: unrecognized option '{flag_str}'")
        return

    key = flag_lookup[flag_str]

    if _param_type(key, spec) is bool:
        result.flags[key] = True
        return

    if value is not None:
        result.flags[key] = value
        return

    try:
        result.flags[key] = next(args_iter)
    except StopIteration:
        errors.append(f"{command_name}: option '{flag_str}' requires an argument")


def _parse_short_chain(
    arg: str,
    flag_lookup: dict[str, str],
    spec: dict[str, dict],
    command_name: str,
    args_iter: iter,
    result: ParseResult,
    errors: list[str],
) -> None:
    """Parse a short-flag token which may contain combined flags (``-abc``).

    Each character after the leading ``-`` is treated as a separate flag.
    When a value-taking flag is encountered:
    - If followed by more characters, those characters become the value.
    - If it is the last character, the next argument is consumed as the value.
    """
    chars = arg[1:]

    for idx, char in enumerate(chars):
        flag_str = f"-{char}"

        if flag_str not in flag_lookup:
            errors.append(f"{command_name}: invalid option -- '{char}'")
            continue

        key = flag_lookup[flag_str]

        if _param_type(key, spec) is bool:
            result.flags[key] = True
            continue

        # Value-taking parameter
        remaining = chars[idx + 1:]
        if remaining:
            result.flags[key] = remaining
            break

        try:
            result.flags[key] = next(args_iter)
        except StopIteration:
            errors.append(
                f"{command_name}: option requires an argument -- '{char}'"
            )
        break
