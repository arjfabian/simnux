from typing import List
from kernel.command import SimnuxCommand

class Command(SimnuxCommand):
    name = "cat"

    def execute(self, args: List[str]) -> str:
        # 1. Validate that there are arguments
        if not args:
            # In Linux, "cat" without arguments waits for STDIN.
            # For now, SIMNUX will fail silently.
            return "" 

        target = args[0]
        
        # 2. Resolve the absolute path (this supports relative paths and "..")
        abs_path = self.session.vfs._resolve_path(self.session.current_path, target)

        # 3. Verify if it's a directory (cat can not read directories)
        if self.session.vfs.is_dir(abs_path):
            return f"[[error]]cat: {target}: Is a directory[[/]]"

        # 4. Try to read the file from the VFS (Layered logic: Delta -> Base)
        content = self.session.vfs.read_file(abs_path)

        # 5. If the file exists, return its contents (it may be empty)
        if content is not None:
            return content
        
        # 5. If the file does not exist, return an error
        return f"[[error]]cat: {target}: No such file or directory[[/]]"