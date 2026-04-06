from typing import List
from kernel.command import SimnuxCommand

class Command(SimnuxCommand):
    name = "pwd"

    def execute(self, args: List[str]) -> str:
        return self.session.current_path