from simnux.runtime.models import CommandResult


class CommandDispatcher:
    """Thin dispatch layer that resolves command names to instances and
    delegates execution.

    Precondition: the caller must verify command existence via
    ``registry.exists()`` before calling ``dispatch()``.
    """

    def __init__(self, registry):
        self.registry = registry

    def dispatch(self, cmd_name: str, args: list[str]) -> CommandResult:
        """Execute a registered command."""

        command = self.registry.get(cmd_name)

        if command is None:
            raise ValueError(f"Command not registered: {cmd_name}")

        return command.execute(args)
