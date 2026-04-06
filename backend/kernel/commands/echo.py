from typing import List
from kernel.command import SimnuxCommand

class Command(SimnuxCommand):
    name = "echo"

    def execute(self, args: List[str]) -> str:
        if not args:
            return ""
        # Flatten the array
        message = ' '.join(args)
        # In Linux, if a string begins with a single or double quote, but ends
        # without one, "echo" waits for STDIN.
        # For now, the command will detect whether the input is enclosed in
        # single or double quotes, remove them, and return the result.
        if len(message) >= 2:
            first, last = message[0], message[-1]
            if first == last and first in ("\"", "'"):
                message = message[1:-1]
        return message