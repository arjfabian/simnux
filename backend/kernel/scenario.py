import os
from typing import Dict, Any
import yaml

class Scenario:
    def __init__(self, scenario_path: str):
        self.config = self._load_from_yaml(scenario_path)
        self.name = self.config.get("name", None)
        self.filesystem = self.config.get("filesystem", None)
        self.username = self.config.get("username", None)
        self.hostname = self.config.get("hostname", None)
        self.starting_dir = self.config.get("starting_dir", None)
        self.motd = self.config.get("motd", None)

        if not all (_ for _ in [self.name, self.filesystem, self.username, self.hostname]):
            raise Exception("Some or more parameters are not defined. The scenario can not be loaded.")

    def _load_from_yaml(self, scenario_path: str):
        file_path = os.path.join(scenario_path, "scenario.yml")
        with open(file_path, 'r') as f:
            return yaml.safe_load(f)

    def get_initial_fs_state(self):
        return self.filesystem
