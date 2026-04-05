from kernel.scenario import Scenario
from filesystem import VFS
import os
import importlib.util
import inspect
from kernel.command import SimnuxCommand

class SimnuxShell:
    def __init__(self, session_id: str, scenario_path: str, logger=None):
        self.session_id = session_id

        # 1. Load the scenario
        self.scenario = Scenario(scenario_path)
        self.logger = logger
        
        # 2. Initialize VFS (taken from the scenario definitions)
        self.vfs = VFS(
            base_state=self.scenario.get_initial_fs_state(),
            session=self,
            logger=logger
        )
        
        # 3. Setup identity (taken from the scenario definitions)
        self.username = self.scenario.username
        self.hostname = self.scenario.hostname
        self.current_path = self.scenario.starting_dir
        self.motd = self.scenario.motd

        # 4. Command load (Kernel + Scenario Tools)
        self.commands = {}
        self._discover_all_commands(scenario_path)

    def _log(self, message: str): self.logger.add(message)

    def get_prompt(self) -> str:
        # The Shell builds the string that the frontend will show
        path = self.current_path
        if self.username == "root":
            if path == "/root": path = "~"
            tail = "#"
        else:
            if path == f"/home/{self.username}": path = "~"
            tail = "$"
        return f"{self.username}@{self.hostname}:{path}{tail} "

    def get_motd(self) -> dict:
        """Returns the formatted MOTD as a successful response."""
        return self._build_response(output=self.motd+"\n")

    def get_status(self) -> dict:
        """Useful for the /initialize endpoint"""
        return {
            "tasks_total": 0,
            "tasks_completed": 0,
            "scenario_solved": False
        }

    def dispatch(self, raw_input: str) -> dict:
        parts = raw_input.strip().split()
        if not parts:
            return self._build_response("")

        cmd_name = parts[0]
        args = parts[1:]

        if cmd_name in self.commands:
            try:
                output = self.commands[cmd_name].execute(args)
                error = None
            except Exception as e:
                output = ""
                error = f"Runtime Error: {str(e)}"
        else:
            output = ""
            error = f"simnux: {cmd_name}: command not found"

        return self._build_response(output, error)

    def _discover_all_commands(self, scenario_path: str):
        """Discovery orchestrator: Kernel -> Scenario"""
        # 1. Load base commands from the kernel
        kernel_cmds_path = os.path.join(os.path.dirname(__file__), "commands")
        self._log(f"Initiating content discovery in directory {kernel_cmds_path}.")
        self._load_from_directory(kernel_cmds_path)
        
        # 2. Load Scenario-specific commands (can override base commands)
        scenario_tools_path = os.path.join(scenario_path, "tools")
        if os.path.exists(scenario_tools_path):
            self._load_from_directory(scenario_tools_path)

    def _load_from_directory(self, directory: str):
        """Scans a folder looking for the 'Command' object in each .py file"""
        if not os.path.exists(directory):
            return

        for filename in os.listdir(directory):
            if filename.endswith(".py") and not filename.startswith("__"):
                module_name = filename[:-3]
                file_path = os.path.join(directory, filename)
                
                try:
                    # 1. Create specification and import module
                    spec = importlib.util.spec_from_file_location(module_name, file_path)
                    if spec is None: continue
                    
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)

                    # 2. Look for the 'Command' class
                    if hasattr(module, "Command"):
                        cmd_class = getattr(module, "Command")
                        
                        # Check if there is an "execute" function
                        if inspect.isclass(cmd_class) and hasattr(cmd_class, "execute"):
                            instance = cmd_class(self)
                            
                            cmd_key = getattr(instance, 'name', module_name)
                            self.commands[cmd_key] = instance
                            self._log(f"Successfully attached command: {cmd_key}")
                            
                except Exception as e:
                    # It's important to catch errors here so a broken command
                    # doesn't bring the whole kernel down.
                    print(f"Kernel Error: Could not load {filename}: {e}")

    def _build_response(self, output, error=None):
        return {
            "output": output,
            "error": error,
            "prompt": self.get_prompt(),
            "session_id": str(self.session_id),
            "status": self.get_status()
        }

