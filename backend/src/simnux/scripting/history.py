"""POSIX history expansion engine for interactive shell sessions."""

import re


class CommandHistory:
    """POSIX history expansion over a shared history list.

    Wraps an existing ``list[str]`` (typically ``SNXSession.history``)
    and provides bash-style expansion tokens before command tokenization.

    Supported tokens:

    - ``!!`` — most recent command.
    - ``!n`` — 1-indexed history number.
    - ``!-n`` — relative past command (n lines back).
    - ``!string`` — most recent command starting with *string*.
    """

    def __init__(self, entries: list[str]) -> None:
        self._entries = entries

    @property
    def entries(self) -> list[str]:
        return list(self._entries)

    def expand(self, raw_cmd: str) -> tuple[str, bool]:
        """Expand POSIX history tokens in *raw_cmd*.

        Returns ``(expanded, was_expanded)`` where *was_expanded* is
        ``True`` if any substitution occurred.

        Raises ``ValueError`` if an expansion token matches no event.
        """
        if not raw_cmd or "!" not in raw_cmd:
            return raw_cmd, False

        result = raw_cmd
        expanded = False

        pattern = re.compile(r"!!|!(-?\d+)|!([a-zA-Z][a-zA-Z0-9]*)")

        def _replace(m: re.Match) -> str:
            nonlocal expanded
            token = m.group(0)

            if token == "!!":
                if not self._entries:
                    raise ValueError("bash: !!: event not found")
                expanded = True
                return self._entries[-1]

            if m.group(1) is not None:
                n = int(m.group(1))
                if n == 0:
                    raise ValueError(f"bash: {token}: event not found")
                idx = n - 1 if n > 0 else len(self._entries) + n
                if idx < 0 or idx >= len(self._entries):
                    raise ValueError(f"bash: {token}: event not found")
                expanded = True
                return self._entries[idx]

            if m.group(2) is not None:
                prefix = m.group(2)
                for entry in reversed(self._entries):
                    if entry.startswith(prefix):
                        expanded = True
                        return entry
                raise ValueError(f"bash: {token}: event not found")

            return token

        result = pattern.sub(_replace, result)
        return result, expanded
