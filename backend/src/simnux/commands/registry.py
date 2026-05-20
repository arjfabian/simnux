"""In-memory registry for SIMNUX command instances."""

from .runtime import SNXCommand


class CommandRegistry:
    """String-keyed map of command name -> SNXCommand instance.

    Registration happens once per session at init time; registry is read-only
    during execution. No duplicate detection — last registration wins.
    """

    def __init__(self) -> None:
        self._commands: dict[str, SNXCommand] = {}

    def register(self, command: SNXCommand) -> None:
        """Register a command instance under its declared name."""
        self._commands[command.name] = command

    def get(self, name: str) -> SNXCommand | None:
        """Return a command instance or None if not registered."""
        return self._commands.get(name)

    def exists(self, name: str) -> bool:
        """Check whether a command is available in the registry."""
        return name in self._commands

    def list_commands(self) -> list[str]:
        """Return sorted list of available command names."""
        return sorted(self._commands.keys())
