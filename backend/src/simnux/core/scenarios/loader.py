"""
Scenario loader for SIMNUX.

Transforms declarative YAML scenarios into in-memory filesystem and
runtime-ready structures.
"""

from pathlib import Path

import yaml

from simnux.core.filesystem.models import PermissionPresets
from simnux.core.filesystem.models import SNXNode
from simnux.security.groups.models import SNXGroup
from simnux.security.users.models import SNXUser

from .models import SNXScenario


class ScenarioNotFoundError(FileNotFoundError):
    """Raised when a scenario directory or ``scenario.yaml`` does not exist."""


class ScenarioLoader:
    """Load and normalize SIMNUX scenario definitions from disk.

    Scenarios are stored under ``scenarios/<name>/scenario.yaml`` relative
    to the project root. The loader constructs the full directory tree from
    flat filesystem declarations, auto-creating parent directories.

    Lightweight contract defaults are applied for missing YAML fields:

        ``hostname``    → ``"simnux"``
        ``starting_dir`` → ``"/home/user"``
        ``win_message`` → ``"Scenario objective completed successfully!"``
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
    def _get_path_owner(
        cls,
        path: str,
        users: dict[str, SNXUser],
        groups: dict[str, SNXGroup],
    ) -> tuple[SNXUser, SNXGroup]:
        """Return the owner and group for a filesystem path.

        Paths under ``/home/<username>`` belong to that user and their
        primary group. All other paths belong to ``root:root``.
        """
        for identifier, user in users.items():
            if identifier == "root":
                continue

            home = f"/home/{identifier}"

            if path == home or path.startswith(f"{home}/"):
                return user, groups[identifier]

        return users["root"], groups["root"]

    @classmethod
    def load(cls, scenario_name: str) -> SNXScenario:
        scenario_path = cls._get_scenarios_dir() / scenario_name / "scenario.yaml"

        if not scenario_path.exists():
            raise ScenarioNotFoundError(f"Scenario '{scenario_name}' not found at {scenario_path}")

        raw = yaml.safe_load(scenario_path.read_text(encoding="utf-8"))

        # Initialize groups and users.
        groups = {"root": SNXGroup(0, "root")}
        users = {"root": SNXUser(0, "root")}

        for user_data in raw.get("users", []):
            user = SNXUser(
                user_id=user_data["user_id"],
                identifier=user_data["identifier"],
            )

            group = SNXGroup(
                group_id=user.user_id,
                identifier=user.identifier,
            )

            users[user.identifier] = user
            groups[group.identifier] = group

        # Initialize filesystem.
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

        for path, is_directory in sorted(paths, key=lambda item: item[0].count("/")):
            if not is_directory:
                continue

            owner, group = cls._get_path_owner(path, users, groups)

            filesystem[path] = SNXNode(
                path=path,
                owner=owner,
                group=group,
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

            owner, group = cls._get_path_owner(normalized, users, groups)

            filesystem[normalized] = SNXNode(
                path=normalized,
                owner=owner,
                group=group,
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

        return SNXScenario(
            name=raw["name"],
            difficulty=raw["difficulty"],
            hostname=raw.get("hostname", "simnux"),
            users=users,
            groups=groups,
            starting_dir=starting_dir,
            filesystem=filesystem,
            objective=objective,
            triggers=raw.get("triggers"),
        )

    @classmethod
    def list_available(cls) -> list[str]:
        """Return sorted list of valid scenario directory names."""
        scenarios_dir = cls._get_scenarios_dir()

        if not scenarios_dir.is_dir():
            return []

        return [
            entry.name
            for entry in sorted(scenarios_dir.iterdir())
            if entry.is_dir() and (entry / "scenario.yaml").is_file()
        ]
