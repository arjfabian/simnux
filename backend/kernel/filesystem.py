import os

class VFS:
    def __init__(self, base_state: dict, session=None, logger=None):
        self.base_state = base_state     # Read-Only -- From Scenario Definition
        self.deltas = {}                               # Read-Write for the user
        self.session = session
        self.logger = logger

    def _log(self, message: str):
        if self.logger:
            self.logger.add(message)

    def read_file(self, path):
        # Layered logic: Delta -> Base
        return self.deltas.get(path, self.base_state.get(path))

    def write_file(self, path: str, content: str):
        """
        Instead of touching self.base_state, we record changes as deltas.
        """
        # TODO: Implement real 'diff' logic if the file is huge. For now, we
        # store the full string for the modified file.
        self.deltas[path] = content
        self._log(f"VFS: Delta applied on {path}")

    def _build_dir_map(self, paths):
        dirs = set(["/"])
        for p in paths:
            parts = p.split("/")
            # If the path is /etc/ssh/config, we add /etc and /etc/ssh
            for i in range(2, len(parts)):
                dirs.add("/" + "/".join(parts[1:i]))
        return dirs

    def list_dir(self, path: str) -> list:
        # 1. Normalize the search path
        search_prefix = path if path.endswith("/") else f"{path}/"
        # 2. Gather the keys from the base state and user deltas
        all_paths = set(list(self.base_state.keys()) + list(self.deltas.keys()))
        entries = set()
        # 3. Process each path in the general set
        for p in all_paths:
            if p.startswith(search_prefix):
                elem = p[len(search_prefix):]
                # Identify paths corresponding to directories (contain a '/')
                file_limit = elem.find("/")
                if file_limit > 0:
                    elem = elem[:file_limit+1]
                entries.add(elem)
        return sorted(list(entries))

    def exists(self, path: str) -> bool:
        return path in self.base_state or path in self.deltas

    def is_dir(self, path: str) -> bool:
        all_paths = list(self.base_state.keys()) + list(self.deltas.keys())
        return any(p.startswith(path.rstrip('/') + '/') for p in all_paths)

    def get_delta_size(self) -> int:
        """Useful for debug: how much RAM is the user session taking up?"""
        return sum(len(v) for v in self.deltas.values())

    def home_dir(self):
        if not self.session:
            return "/"
        user = self.session.username
        return "/root" if user == "root" else f"/home/{user}"

    def _resolve_path(self, current_dir: str, target_path: str) -> str:
        # 1. Resolve "~" to "/home"
        if target_path.startswith("~"):
            home = self.home_dir()
            target_path = target_path.replace("~", home, 1)

        # 2. If the path is relative, add the current directory as a prefix.
        if target_path.startswith("/"):
            absolute = target_path
        else:
            absolute = os.path.join(current_dir, target_path)
            
        # 3. Remove instances of "." and ".."
        normalized = os.path.normpath(absolute)
        
        # 4. Symbolic chroot: Force the directory inside the root ("/")
        if not normalized.startswith("/"):
            normalized = "/"
            
        return normalized