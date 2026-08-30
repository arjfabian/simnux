"""Command base class defining the execution contract and shared utilities."""

from abc import ABC
from abc import abstractmethod
import logging

from simnux.core.commands.argument_parser import ParseResult
from simnux.core.commands.models import CommandContext
from simnux.core.commands.streams import AsyncStreamReader
from simnux.core.commands.streams import AsyncStreamWriter
from simnux.core.runtime.models import ExitCode
from simnux.core.runtime.models import TerminalAction


logger = logging.getLogger("simnux.commands")


class SNXCommand(ABC):
    """Abstract base for all shell commands."""

    name: str = ""
    aliases: list[str] = []
    args: list[str] | None = None
    action_type: TerminalAction = TerminalAction.NONE
    parameters: dict[str, dict] = {}
    parsed_args: ParseResult | None = None
    _invoked_name: str = ""

    def __init__(self, context) -> None:
        if not self.name:
            raise ValueError(f"{self.__class__.__name__} must define a command name")

        self.context = context

    @abstractmethod
    async def execute(
        self,
        ctx: CommandContext,
        stdin: AsyncStreamReader,
        stdout: AsyncStreamWriter,
        stderr: AsyncStreamWriter,
    ) -> ExitCode:
        """Execute with a CommandContext and I/O streams.

        The dispatcher provides live streams — write output to stdout,
        errors to stderr, return an ExitCode. Side effects limited to
        ctx.session and ctx.filesystem.delta_layer.
        """
        raise NotImplementedError

    @property
    def help_text(self) -> str:
        return "No help available for this command."

    def normalize_args(self, args: list[str]) -> list[str]:
        """Pre-process raw args before execution.

        Override for command-specific quirks (e.g. head -3 shorthand).
        Must not mutate self.args.
        """
        return args

    def resolve_path(self, target: str, ctx: CommandContext | None = None) -> str:
        """Resolve a user path to an absolute VFS path using session CWD."""
        ctx = ctx or self.context
        session = ctx.session

        return ctx.filesystem.resolve_path(
            current_directory=session.current_directory,
            target_path=target,
            home_directory=session.home_directory,
        )
