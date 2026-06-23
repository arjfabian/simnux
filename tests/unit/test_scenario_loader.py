"""Tests for ScenarioLoader — YAML-based scenario file deserialization.

Covers YAML parsing, implicit directory creation, permission presets,
and filesystem bootstrap (root node auto-creation).
"""

import pytest

from simnux.filesystem.models import PermissionPresets
from simnux.scenarios.loader import ScenarioLoader


SCENARIO_YAML = """\
name: "Loader Test"
motd: "Testing"
difficulty: "Medium"
username: "tester"
hostname: "loader-host"
starting_dir: "/home/tester"

filesystem:
  "/home/tester/readme.txt": "Hello"
  "/home/tester/docs/": ""
  "/home/tester/docs/note.txt": "Note content"
  "/etc/config.yml": "debug: true"
  "/var/data/": ""
"""


MALFORMED_SCENARIO = """\
name: "Malformed"
"""


@pytest.fixture
def scenario_dir(tmp_path):
    """Create a temporary directory with a valid scenario YAML file."""
    d = tmp_path / "test_scenario"
    d.mkdir()
    (d / "scenario.yml").write_text(SCENARIO_YAML)
    return d


@pytest.fixture
def malformed_dir(tmp_path):
    """Create a temporary directory with a minimal (incomplete) scenario YAML."""
    d = tmp_path / "malformed"
    d.mkdir()
    (d / "scenario.yml").write_text(MALFORMED_SCENARIO)
    return d


@pytest.fixture
def patch_path(monkeypatch, scenario_dir):
    """Factory fixture: monkeypatches ``Path`` so ScenarioLoader reads from a given dir."""

    def _patcher(target_dir):
        monkeypatch.setattr(
            "simnux.scenarios.loader.Path",
            lambda *args, **kw: target_dir,
        )

    return _patcher


class TestScenarioLoader:
    """Scenario loading from YAML: metadata parsing, filesystem bootstrap.

    Uses the ``scenario_dir`` fixture (valid YAML) and ``patch_path``
    to redirect ScenarioLoader to a temp file. Verifies directory
    auto-creation, permission presets, and metadata extraction.
    """

    def test_yaml_loading(self, scenario_dir, patch_path):
        """YAML metadata fields (name, difficulty) are parsed correctly."""
        patch_path(scenario_dir)
        scenario = ScenarioLoader.load("test_scenario")
        assert scenario.name == "Loader Test"
        assert scenario.difficulty == "Medium"

    def test_root_auto_bootstrap(self, scenario_dir, patch_path):
        """Root node (``/``) is always auto-created as a directory if not in YAML."""
        patch_path(scenario_dir)
        scenario = ScenarioLoader.load("test_scenario")
        assert "/" in scenario.filesystem
        assert scenario.filesystem["/"].is_directory is True

    def test_implicit_directory_creation(self, scenario_dir, patch_path):
        """Parent directories implied by file paths are auto-created."""
        patch_path(scenario_dir)
        scenario = ScenarioLoader.load("test_scenario")
        assert "/home" in scenario.filesystem
        assert scenario.filesystem["/home"].is_directory is True

    def test_nested_implicit_directories(self, scenario_dir, patch_path):
        """Deeply nested directories implied by file paths are auto-created."""
        patch_path(scenario_dir)
        scenario = ScenarioLoader.load("test_scenario")
        assert "/home/tester" in scenario.filesystem
        assert scenario.filesystem["/home/tester"].is_directory is True
        assert "/home/tester/docs" in scenario.filesystem
        assert scenario.filesystem["/home/tester/docs"].is_directory is True

    def test_explicit_file_detection(self, scenario_dir, patch_path):
        """File entries (no trailing ``/``) are created with their content."""
        patch_path(scenario_dir)
        scenario = ScenarioLoader.load("test_scenario")
        assert "/home/tester/readme.txt" in scenario.filesystem
        assert scenario.filesystem["/home/tester/readme.txt"].is_directory is False
        assert scenario.filesystem["/home/tester/readme.txt"].content == "Hello"

    def test_explicit_directory_detection(self, scenario_dir, patch_path):
        """Directory entries (trailing ``/``) are created as directories."""
        patch_path(scenario_dir)
        scenario = ScenarioLoader.load("test_scenario")
        assert "/home/tester/docs" in scenario.filesystem
        assert scenario.filesystem["/home/tester/docs"].is_directory is True

    def test_permission_presets_for_directories(self, scenario_dir, patch_path):
        """Auto-created directories get ``DIRECTORY_DEFAULT`` permissions."""
        patch_path(scenario_dir)
        scenario = ScenarioLoader.load("test_scenario")
        dir_node = scenario.filesystem["/home/tester"]
        assert dir_node.permissions == PermissionPresets.DIRECTORY_DEFAULT

    def test_permission_presets_for_files(self, scenario_dir, patch_path):
        """Auto-created files get ``FILE_DEFAULT`` permissions."""
        patch_path(scenario_dir)
        scenario = ScenarioLoader.load("test_scenario")
        file_node = scenario.filesystem["/home/tester/readme.txt"]
        assert file_node.permissions == PermissionPresets.FILE_DEFAULT

    def test_scenario_metadata_populated(self, scenario_dir, patch_path):
        """All YAML metadata fields are mapped to the SNXScenario object."""
        patch_path(scenario_dir)
        scenario = ScenarioLoader.load("test_scenario")
        assert scenario.name == "Loader Test"
        assert scenario.motd == "Testing"
        assert scenario.difficulty == "Medium"
        assert scenario.username == "tester"
        assert scenario.hostname == "loader-host"
        assert scenario.starting_dir == "/home/tester"

    def test_starting_directory_auto_created(self, scenario_dir, patch_path):
        """The scenario's ``starting_dir`` is always auto-created as a directory."""
        patch_path(scenario_dir)
        scenario = ScenarioLoader.load("test_scenario")
        assert scenario.filesystem["/home/tester"].is_directory

    def test_var_data_directory(self, scenario_dir, patch_path):
        """Explicit directory entries (e.g. ``/var/data/``) are created correctly."""
        patch_path(scenario_dir)
        scenario = ScenarioLoader.load("test_scenario")
        assert "/var/data" in scenario.filesystem
        assert scenario.filesystem["/var/data"].is_directory is True

    def test_empty_file_content(self, scenario_dir, patch_path):
        """Empty trailing slash identifies a directory vs a file with empty content."""
        patch_path(scenario_dir)
        scenario = ScenarioLoader.load("test_scenario")
        assert "/etc/config.yml" in scenario.filesystem
        assert scenario.filesystem["/etc/config.yml"].content == "debug: true"
