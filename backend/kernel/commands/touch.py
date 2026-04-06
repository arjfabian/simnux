from typing import List
from kernel.command import SimnuxCommand

class Command(SimnuxCommand):
    name = "touch"

    def execute(self, args: List[str]) -> str:
        if not args:
            return "[[error]]touch: missing file operand[[/]]"

        target = args[0]
        # Use the VFS resolver to handle relative paths
        abs_path = self.session.vfs._resolve_path(self.session.current_path, target)

        # If file exists, we 'update' it (in SimFS we just write empty if new, 
        # or keep content if exists, simulating timestamp update)
        if not self.session.vfs.exists(abs_path):
            self.session.vfs.write_file(abs_path, "")
        
        return "" # touch usually produces no output on success