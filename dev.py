"""Development launcher for SIMNUX.

Runs backend and frontend processes concurrently and coordinates a clean
shutdown lifecycle for local development.
"""

from __future__ import annotations

import atexit
from pathlib import Path
import signal
import subprocess
import sys


ROOT = Path(__file__).parent
BACKEND = ROOT / "backend"
PYTHON = BACKEND / ".venv" / "bin" / "python"


class DevEnvironment:
    """Minimal process supervisor for the local SIMNUX environment."""

    def __init__(self) -> None:
        self.processes: list[subprocess.Popen] = []
        self._shutting_down = False

    def start(self, command: list[str]) -> None:
        """Spawn and track a child process."""

        self.processes.append(subprocess.Popen(command))

    def shutdown(self, *_) -> None:
        """Terminate all managed child processes safely."""

        if self._shutting_down:
            return

        self._shutting_down = True

        print("\nShutting down SIMNUX dev environment...")

        for proc in self.processes:
            if proc.poll() is None:
                proc.terminate()

        for proc in self.processes:
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()

        print("\nThank you for trying SIMNUX.")
        sys.exit(0)

    def run(self) -> None:
        """Start backend/frontend services and block until shutdown."""

        signal.signal(signal.SIGINT, self.shutdown)
        signal.signal(signal.SIGTERM, self.shutdown)

        atexit.register(self.shutdown)

        self.start(
            [
                str(PYTHON),
                "-m",
                "simnux",
            ]
        )

        self.start(
            [
                "python3",
                "-m",
                "http.server",
                "8001",
                "-d",
                str(ROOT / "frontend"),
            ]
        )

        for proc in self.processes:
            proc.wait()


def main() -> None:
    """Entrypoint for the local development environment."""

    DevEnvironment().run()


if __name__ == "__main__":
    main()
