"""
Base class for all SIMNUX commands.

Defines the execution contract and shared utilities for path resolution.
Commands are stateless beyond their injected execution context.
"""

from abc import ABC
from abc import abstractmethod
import logging

from simnux.commands.models import CommandContext
from simnux.commands.streams import AsyncStreamReader
from simnux.commands.streams import AsyncStreamWriter
from simnux.runtime.models import ExitCode


logger = logging.getLogger("simnux.commands")


class SNXCommand(ABC):
    """Abstract base class for all shell commands."""

    name: str = ""
    args: list[str] | None = None

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
        """Execute the command with a ``CommandContext`` and I/O streams.

        The dispatcher always provides live streams — commands write
        output to ``stdout``, errors to ``stderr``, and return an
        ``ExitCode``. ``CommandResult`` is built by the dispatcher from
        the drained stream queues after execution.
        Side effects are limited to ``ctx.session`` and
        ``ctx.filesystem.delta_layer`` — base_layer is never mutated.
        """
        raise NotImplementedError

    @property
    def help_text(self) -> str:
        """Optional help string for future CLI introspection system."""
        return "No help available for this command."

    def resolve_path(self, target: str, ctx: CommandContext | None = None) -> str:
        """Resolve a user-provided path using session-aware filesystem rules.

        Precondition: ``ctx.session.current_directory`` is an absolute,
        normalized path. Returns an absolute path suitable for VFS operations.
        When ``ctx`` is omitted, falls back to ``self.context`` (legacy path).
        """

        ctx = ctx or self.context
        session = ctx.session

        return ctx.filesystem.resolve_path(
            current_directory=session.current_directory,
            target_path=target,
            home_directory=session.home_directory,
        )
