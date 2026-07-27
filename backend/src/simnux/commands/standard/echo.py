import re

from simnux.commands.models import CommandContext
from simnux.commands.runtime import SNXCommand
from simnux.commands.streams import AsyncStreamReader
from simnux.commands.streams import AsyncStreamWriter
from simnux.runtime.models import ExitCode


_ESCAPE_RE = re.compile(
    r"\\(?:"
    r"[abefnrtv\\]"
    r"|0[0-7]{1,3}"
    r"|x[0-9a-fA-F]{1,2}"
    r"|u[0-9a-fA-F]{1,4}"
    r"|U[0-9a-fA-F]{1,8}"
    r")"
)


_ESCAPES: dict[str, str] = {
    "a": "\a",
    "b": "\b",
    "e": "\x1b",
    "f": "\f",
    "n": "\n",
    "r": "\r",
    "t": "\t",
    "v": "\v",
    "\\": "\\",
}


def _interpret_escapes(s: str) -> str:
    """Interpret backslash escape sequences in *s*.

    Supports: ``\\``, ``\\a``, ``\\b``, ``\\e``, ``\\f``, ``\\n``,
    ``\\r``, ``\\t``, ``\\v``, ``\\0nnn`` (octal), ``\\xHH`` (hex),
    ``\\uHHHH`` (unicode), ``\\UHHHHHHHH`` (unicode).
    """

    def _replace(m: re.Match) -> str:
        full = m.group(0)
        char = full[1]

        if char in _ESCAPES:
            return _ESCAPES[char]

        if full.startswith("\\0"):
            digits = full[2:]
            return chr(int(digits, 8) & 0xFF)

        if full.startswith("\\x"):
            digits = full[2:]
            return chr(int(digits, 16) & 0xFF)

        if full.startswith("\\u"):
            digits = full[2:]
            return chr(int(digits, 16))

        if full.startswith("\\U"):
            digits = full[2:]
            return chr(int(digits, 16))

        return full

    return _ESCAPE_RE.sub(_replace, s)


class Command(SNXCommand):
    """POSIX-style echo with ``-n``, ``-e``, and ``-E`` flag support.

    Flags must appear before any positional arguments.  Once a
    non-flag token is encountered, the remaining tokens are treated as
    text to output.

    * ``-n`` — suppress the trailing newline.
    * ``-e`` — enable interpretation of backslash escapes (``\\n``,
      ``\\t``, ``\\\\``, etc.).
    * ``-E`` — disable interpretation of backslash escapes (default).
    """

    name = "echo"

    async def execute(
        self,
        ctx: CommandContext,
        stdin: AsyncStreamReader,
        stdout: AsyncStreamWriter,
        stderr: AsyncStreamWriter,
    ) -> ExitCode:
        args = self.args or []

        no_newline = False
        interpret_escapes = False
        i = 0

        while i < len(args):
            token = args[i]
            if token == "-n":
                no_newline = True
                i += 1
            elif token == "-e":
                interpret_escapes = True
                i += 1
            elif token == "-E":
                interpret_escapes = False
                i += 1
            else:
                break

        output_args = args[i:]
        if not output_args:
            if not no_newline:
                await stdout.write("\n")
            return ExitCode.SUCCESS

        text = " ".join(output_args)
        if interpret_escapes:
            text = _interpret_escapes(text)

        await stdout.write(text)

        return ExitCode.SUCCESS
