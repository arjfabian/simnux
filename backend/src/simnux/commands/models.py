"""
Shared execution context injected into all SIMNUX commands.

Provides controlled access to session state and the virtual filesystem.
"""

from dataclasses import dataclass

from simnux.filesystem.vfs import SNXFileSystem
from simnux.sessions.runtime import SNXSession


@dataclass
class CommandContext:
    """Per-session injection container for command execution.

    Contains references to the mutable session state and filesystem;
    commands share the same context object for their lifetime.
    """

    session: SNXSession
    filesystem: SNXFileSystem
