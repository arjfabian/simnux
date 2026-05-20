"""
Scenario loader for SIMNUX.

Transforms declarative YAML scenarios into in-memory filesystem and
runtime-ready structures.
"""

import yaml

from pathlib import Path

from simnux.filesystem.models import PermissionPresets, SNXNode

from .models import SNXScenario


class ScenarioLoader:
    """Load and normalize SIMNUX scenario definitions from disk.

    Scenario YAML files are searched under ``scenarios/<name>/scenario.yml``.
    The loader constructs the full directory tree from flat filesystem
    declarations, auto-creating parent directories.
    """

    @staticmethod
    def load(scenario_name: str) -> SNXScenario:
        scenario_path = (
            Path(__file__).parent / scenario_name / "scenario.yml"
        )

        with open(scenario_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)

        filesystem: dict[str, SNXNode] = {}
        raw_filesystem = raw.get("filesystem", {})

        paths: set[tuple[str, bool]] = set()

        # Auto-create parent directories for all declared paths and the
        # starting directory
        paths.add(("/", True))

        starting_dir = raw["starting_dir"]
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

            filesystem[normalized] = SNXNode(
                path=normalized,
                content=content,
                is_directory=False,
                permissions=PermissionPresets.FILE_DEFAULT,
            )

        return SNXScenario(
            name=raw["name"],
            motd=raw["motd"],
            difficulty=raw["difficulty"],
            username=raw["username"],
            hostname=raw["hostname"],
            starting_dir=raw["starting_dir"],
            filesystem=filesystem,
        )
