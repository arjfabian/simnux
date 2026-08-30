import importlib
import inspect
import pkgutil

import simnux.core.commands.standard as standard_commands

from .runtime import SNXCommand


class CommandLoader:
    """Auto-discovery eliminates manual registration.

    Every class in ``commands.standard/`` that extends ``SNXCommand`` is
    automatically registered at session init.
    """

    def __init__(
        self,
        registry,
        context,
        logger,
    ) -> None:
        self.registry = registry
        self.context = context
        self.logger = logger

    def load_all(self) -> None:
        """Iterate ``commands.standard`` package via pkgutil and register every
        concrete ``SNXCommand`` subclass. Each command is instantiated with the
        session's ``CommandContext``.
        """

        self.logger.info("Discovering commands")

        for _, module_name, _ in pkgutil.iter_modules(standard_commands.__path__):
            module = importlib.import_module(f"simnux.core.commands.standard.{module_name}")

            self._load_module_commands(module)

    def _load_module_commands(self, module) -> None:
        """Filters for concrete ``SNXCommand`` subclasses (skips the abstract
        base). Commands are stateful per-session — they receive their context
        at instantiation time, not at dispatch time.
        """

        for _, obj in inspect.getmembers(module, inspect.isclass):
            if not issubclass(obj, SNXCommand) or obj is SNXCommand:
                continue

            command = obj(context=self.context)

            self.registry.register(command)

            self.logger.info(f"Loaded command: {command.name}")
