from abc import ABC, abstractmethod

class SimnuxCommand(ABC):
    name: str = None
    def __init__(self, session):
        self.session = session

    @abstractmethod
    def execute(self, args: list) -> str:
        """Executes the command's logic and returns a string."""

    @property
    def help_text(self) -> str:
        return "No help available for this command."