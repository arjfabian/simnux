"""
Base class for all SIMNUX commands.

Defines the execution contract and shared utilities for path resolution.
Commands are stateless beyond their injected execution context.
"""

from abc import ABC, abstractmethod

from simnux.runtime.models import CommandResult


class SNXCommand(ABC):
    """Abstract base class for all shell commands."""

    name: str = ""

    def __init__(self, context) -> None:

        if not self.name:
            raise ValueError(
                f"{self.__class__.__name__} must define a command name"
            )

        self.context = context

    @abstractmethod
    def execute(self, args: list[str]) -> CommandResult:
        """Execute the command with pre-tokenized arguments.

        Returns a ``CommandResult`` with structured stdout/stderr and a
        standardized exit code. Side effects are limited to ``context.session``
        and ``context.filesystem.delta_layer`` — base_layer is never mutated.
        """
        raise NotImplementedError

    @property
    def help_text(self) -> str:
        """Optional help string for future CLI introspection system."""
        return "No help available for this command."

    def resolve_path(self, target: str) -> str:
        """Resolve a user-provided path using session-aware filesystem rules.

        Precondition: ``context.session.current_directory`` is an absolute,
        normalized path. Returns an absolute path suitable for VFS operations.
        """

        session = self.context.session

        return self.context.filesystem.resolve_path(
            current_directory=session.current_directory,
            target_path=target,
            home_directory=session.home_directory,
        )
