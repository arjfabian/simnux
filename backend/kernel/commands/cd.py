from typing import List
from kernel.command import SimnuxCommand

class Command(SimnuxCommand):
    name = "cd"

    def execute(self, args: List[str]) -> str:
        # 1. If there is no argument, default to home directory
        target = args[0] if args else "~"
        # 2. Resolve the new path from the argument        
        new_path = self.session.vfs._resolve_path(self.session.current_path, target)
        
        if self.session.vfs.is_dir(new_path):
            self.session.current_path = new_path
            return ""
        return f"[[error]]cd: {target}: No such directory[[/]]"