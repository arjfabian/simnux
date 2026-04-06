from typing import List
from kernel.command import SimnuxCommand

class Command(SimnuxCommand):
    name = "ls"

    def execute(self, args: List[str]) -> str:
        # 1. Resolve path
        raw_target = args[0] if args else self.session.current_path
        target_path = self.session.vfs._resolve_path(self.session.current_path, raw_target)
        
        # 2. Get the file list from the VFS
        list_of_files = self.session.vfs.list_dir(target_path)
        
        # 3. If VFS tells us this is not a directory, return error
        if not self.session.vfs.is_dir(target_path) and not list_of_files:
             return f"[[error]]ls: cannot access '{raw_target}': No such file or directory[[/]]"

        result = []
        for file in list_of_files:
            if file.endswith("/") or file in [".", ".."]:
                result.append(f"[[dir]]{file[:-1]}[[/]]")
            else:
                result.append(f"[[file]]{file}[[/]]")

        # 4. Add . and ..
        if target_path == "/":
            result = ["[[dir]].[[/]]"] + result
        else:
            result = ["[[dir]].[[/]]", "[[dir]]..[[/]]"] + result

        # 5. Return result
        return "  ".join(result)