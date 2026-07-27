"""
Scenario loader for SIMNUX.

Transforms declarative YAML scenarios into in-memory filesystem and
runtime-ready structures.
"""

from pathlib import Path

import yaml

from simnux.filesystem.models import PermissionPresets
from simnux.filesystem.models import SNXNode

from .models import SNXScenario


class ScenarioNotFoundError(FileNotFoundError):
    """Raised when a scenario directory or ``scenario.yaml`` does not exist."""


class ScenarioLoader:
    """Load and normalize SIMNUX scenario definitions from disk.

    Scenarios are stored under ``scenarios/<name>/scenario.yaml`` relative
    to the project root.  The loader constructs the full directory tree from
    flat filesystem declarations, auto-creating parent directories.

        Lightweight contract defaults are applied for missing YAML fields:
        ``username``      → ``"user"``
        ``hostname``      → ``"simnux"``
        ``starting_dir``  → ``"/home/user"``
        ``win_message``   → ``"Scenario objective completed successfully!"``
    """

    _scenarios_dir: Path | None = None

    @classmethod
    def _get_scenarios_dir(cls) -> Path:
        if cls._scenarios_dir is None:
            cls._scenarios_dir = (
                Path(__file__).resolve().parent.parent.parent.parent.parent / "scenarios"
            )
        return cls._scenarios_dir

    @classmethod
    def load(cls, scenario_name: str) -> SNXScenario:
        scenario_path = cls._get_scenarios_dir() / scenario_name / "scenario.yaml"

        if not scenario_path.exists():
            raise ScenarioNotFoundError(f"Scenario '{scenario_name}' not found at {scenario_path}")

        raw = yaml.safe_load(scenario_path.read_text(encoding="utf-8"))

        filesystem: dict[str, SNXNode] = {}
        raw_filesystem = raw.get("filesystem", {})

        paths: set[tuple[str, bool]] = set()

        paths.add(("/", True))

        starting_dir = raw.get("starting_dir", "/home/user")
        bootstrap_paths = set(raw_filesystem.keys())
        bootstrap_paths.add(starting_dir.rstrip("/") + "/")

        for raw_path in bootstrap_paths:
            is_directory = raw_path.endswith("/")
            normalized = raw_path.rstrip("/") or "/"
            parts = normalized.strip("/").split("/")

            current = ""

            directory_parts = parts if is_directory else parts[:-1]

            for part in directory_parts:
                current += f"/{part}"
                paths.add((current, True))

            paths.add((normalized, is_directory))

        for path, is_directory in sorted(paths, key=lambda x: x[0].count("/")):
            if not is_directory:
                continue

            filesystem[path] = SNXNode(
                path=path,
                content="",
                is_directory=True,
                permissions=PermissionPresets.DIRECTORY_DEFAULT,
            )

        for raw_path, content in raw_filesystem.items():
            if raw_path.endswith("/"):
                continue

            normalized = raw_path.rstrip("/")

            if isinstance(content, list):
                content = "\n".join(content) + "\n"

            filesystem[normalized] = SNXNode(
                path=normalized,
                content=content,
                is_directory=False,
                permissions=PermissionPresets.FILE_DEFAULT,
            )

        objective = raw.get("objective")
        if objective is not None:
            objective.setdefault(
                "win_message",
                "Scenario objective completed successfully!",
            )

        triggers = raw.get("triggers")

        return SNXScenario(
            name=raw["name"],
            difficulty=raw["difficulty"],
            username=raw.get("username", "user"),
            hostname=raw.get("hostname", "simnux"),
            starting_dir=raw.get("starting_dir", "/home/user"),
            filesystem=filesystem,
            objective=objective,
            triggers=triggers,
        )

    @classmethod
    def list_available(cls) -> list[str]:
        """Return sorted list of valid scenario directory names."""
        scenarios_dir = cls._get_scenarios_dir()
        if not scenarios_dir.is_dir():
            return []

        names: list[str] = []
        for entry in sorted(scenarios_dir.iterdir()):
            if entry.is_dir() and (entry / "scenario.yaml").is_file():
                names.append(entry.name)
        return names
