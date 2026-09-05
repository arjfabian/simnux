"""Tests for ScenarioLoader — YAML-based scenario file deserialization.

Covers YAML parsing, implicit directory creation, permission presets,
filesystem bootstrap, contract defaults, and the listing API.
"""

from pathlib import Path

import pytest

from simnux.core.filesystem.models import PermissionPresets
from simnux.core.scenarios.loader import ScenarioLoader
from simnux.core.scenarios.loader import ScenarioNotFoundError


SCENARIO_YAML = """\
name: "Loader Test"
difficulty: "Medium"
hostname: "loader-host"
users:
  - user_id: 1001
    identifier: tester
starting_dir: "/home/tester"

filesystem:
  "/etc/motd": "Testing"
  "/home/tester/readme.txt": "Hello"
  "/home/tester/docs/": ""
  "/home/tester/docs/note.txt": "Note content"
  "/etc/config.yml": "debug: true"
  "/var/data/": ""
"""


MINIMAL_SCENARIO = """\
name: "Minimal"
difficulty: "Easy"
"""


OBJECTIVE_SCENARIO = """\
name: "ObjectiveTest"
difficulty: "Hard"
objective:
  type: "file_state"
  path: "/tmp/flag.txt"
"""


@pytest.fixture
def scenarios_dir(tmp_path):
    """Create a temporary ``scenarios/`` directory with a valid ``hello/`` sub-dir."""
    d = tmp_path / "scenarios"
    d.mkdir()
    return d


@pytest.fixture
def hello_dir(scenarios_dir):
    """Create ``scenarios/hello/scenario.yaml`` with the standard YAML."""
    d = scenarios_dir / "hello"
    d.mkdir()
    (d / "scenario.yaml").write_text(SCENARIO_YAML)
    return d


@pytest.fixture
def minimal_dir(scenarios_dir):
    """Create ``scenarios/minimal/scenario.yaml`` with only name/difficulty."""
    d = scenarios_dir / "minimal"
    d.mkdir()
    (d / "scenario.yaml").write_text(MINIMAL_SCENARIO)
    return d


@pytest.fixture
def objective_dir(scenarios_dir):
    """Create a scenario with an objective (no``win_message`` — verify default)."""
    d = scenarios_dir / "objective_test"
    d.mkdir()
    (d / "scenario.yaml").write_text(OBJECTIVE_SCENARIO)
    return d


@pytest.fixture
def patch_scenarios_dir(monkeypatch):
    """Monkeypatch ``ScenarioLoader._get_scenarios_dir`` to return ``tmp_path / scenarios``."""

    def _patcher(target_dir: Path):
        monkeypatch.setattr(
            ScenarioLoader,
            "_get_scenarios_dir",
            lambda: target_dir,
        )

    return _patcher


class TestScenarioLoader:
    """Scenario loading from YAML: metadata parsing, filesystem bootstrap.

    Uses the ``hello_dir`` fixture (valid YAML) and ``patch_scenarios_dir``
    to redirect ScenarioLoader to a temp directory.
    """

    def test_yaml_loading(self, hello_dir, patch_scenarios_dir):
        """YAML metadata fields (name, difficulty) are parsed correctly."""
        patch_scenarios_dir(hello_dir.parent)
        scenario = ScenarioLoader.load("hello")
        assert scenario.name == "Loader Test"
        assert scenario.difficulty == "Medium"

    def test_root_auto_bootstrap(self, hello_dir, patch_scenarios_dir):
        """Root node (``/``) is always auto-created as a directory if not in YAML."""
        patch_scenarios_dir(hello_dir.parent)
        scenario = ScenarioLoader.load("hello")
        assert "/" in scenario.filesystem
        assert scenario.filesystem["/"].is_directory is True

    def test_implicit_directory_creation(self, hello_dir, patch_scenarios_dir):
        """Parent directories implied by file paths are auto-created."""
        patch_scenarios_dir(hello_dir.parent)
        scenario = ScenarioLoader.load("hello")
        assert "/home" in scenario.filesystem
        assert scenario.filesystem["/home"].is_directory is True

    def test_nested_implicit_directories(self, hello_dir, patch_scenarios_dir):
        """Deeply nested directories implied by file paths are auto-created."""
        patch_scenarios_dir(hello_dir.parent)
        scenario = ScenarioLoader.load("hello")
        assert "/home/tester" in scenario.filesystem
        assert scenario.filesystem["/home/tester"].is_directory is True
        assert "/home/tester/docs" in scenario.filesystem
        assert scenario.filesystem["/home/tester/docs"].is_directory is True

    def test_explicit_file_detection(self, hello_dir, patch_scenarios_dir):
        """File entries (no trailing ``/``) are created with their content."""
        patch_scenarios_dir(hello_dir.parent)
        scenario = ScenarioLoader.load("hello")
        assert "/home/tester/readme.txt" in scenario.filesystem
        assert scenario.filesystem["/home/tester/readme.txt"].is_directory is False
        assert scenario.filesystem["/home/tester/readme.txt"].content == "Hello"

    def test_explicit_directory_detection(self, hello_dir, patch_scenarios_dir):
        """Directory entries (trailing ``/``) are created as directories."""
        patch_scenarios_dir(hello_dir.parent)
        scenario = ScenarioLoader.load("hello")
        assert "/home/tester/docs" in scenario.filesystem
        assert scenario.filesystem["/home/tester/docs"].is_directory is True

    def test_permission_presets_for_directories(self, hello_dir, patch_scenarios_dir):
        """Auto-created directories get ``DIRECTORY_DEFAULT`` permissions."""
        patch_scenarios_dir(hello_dir.parent)
        scenario = ScenarioLoader.load("hello")
        dir_node = scenario.filesystem["/home/tester"]
        assert dir_node.permissions == PermissionPresets.DIRECTORY_DEFAULT

    def test_permission_presets_for_files(self, hello_dir, patch_scenarios_dir):
        """Auto-created files get ``FILE_DEFAULT`` permissions."""
        patch_scenarios_dir(hello_dir.parent)
        scenario = ScenarioLoader.load("hello")
        file_node = scenario.filesystem["/home/tester/readme.txt"]
        assert file_node.permissions == PermissionPresets.FILE_DEFAULT

    def test_scenario_metadata_populated(self, hello_dir, patch_scenarios_dir):
        """All YAML metadata fields are mapped to the SNXScenario object."""
        patch_scenarios_dir(hello_dir.parent)
        scenario = ScenarioLoader.load("hello")
        assert scenario.name == "Loader Test"
        assert scenario.difficulty == "Medium"
        assert scenario.users["tester"].identifier == "tester"
        assert scenario.hostname == "loader-host"
        assert scenario.starting_dir == "/home/tester"

    def test_starting_directory_auto_created(self, hello_dir, patch_scenarios_dir):
        """The scenario's ``starting_dir`` is always auto-created as a directory."""
        patch_scenarios_dir(hello_dir.parent)
        scenario = ScenarioLoader.load("hello")
        assert scenario.filesystem["/home/tester"].is_directory

    def test_var_data_directory(self, hello_dir, patch_scenarios_dir):
        """Explicit directory entries (e.g. ``/var/data/``) are created correctly."""
        patch_scenarios_dir(hello_dir.parent)
        scenario = ScenarioLoader.load("hello")
        assert "/var/data" in scenario.filesystem
        assert scenario.filesystem["/var/data"].is_directory is True

    def test_empty_file_content(self, hello_dir, patch_scenarios_dir):
        """Empty trailing slash identifies a directory vs a file with empty content."""
        patch_scenarios_dir(hello_dir.parent)
        scenario = ScenarioLoader.load("hello")
        assert "/etc/config.yml" in scenario.filesystem
        assert scenario.filesystem["/etc/config.yml"].content == "debug: true"

    def test_minimal_scenario_defaults(self, minimal_dir, patch_scenarios_dir):
        """Minimal YAML (name/difficulty only) gets defaults for missing fields."""
        patch_scenarios_dir(minimal_dir.parent)
        scenario = ScenarioLoader.load("minimal")
        assert scenario.name == "Minimal"
        assert scenario.users["root"].identifier == "root"
        assert scenario.hostname == "simnux"
        assert scenario.starting_dir == "/home/user"

    def test_missing_scenario_raises_error(self, hello_dir, patch_scenarios_dir):
        """Loading a nonexistent scenario raises ScenarioNotFoundError."""
        patch_scenarios_dir(hello_dir.parent)
        with pytest.raises(ScenarioNotFoundError, match="not found"):
            ScenarioLoader.load("nonexistent_scenario")

    def test_list_available(self, hello_dir, minimal_dir, patch_scenarios_dir):
        """``list_available()`` returns sorted scenario directory names."""
        patch_scenarios_dir(hello_dir.parent)
        available = ScenarioLoader.list_available()
        assert "hello" in available
        assert "minimal" in available

    def test_list_available_empty(self, monkeypatch):
        """``list_available()`` returns empty list when scenarios/ does not exist."""
        monkeypatch.setattr(
            ScenarioLoader,
            "_get_scenarios_dir",
            lambda: Path("/tmp/simnux_nonexistent_scenarios_xyz"),
        )
        available = ScenarioLoader.list_available()
        assert available == []

    def test_objective_default_win_message(self, objective_dir, patch_scenarios_dir):
        """``win_message`` defaults to the contract string when omitted from YAML."""
        patch_scenarios_dir(objective_dir.parent)
        scenario = ScenarioLoader.load("objective_test")
        assert scenario.objective is not None
        assert scenario.objective["win_message"] == "Scenario objective completed successfully!"
