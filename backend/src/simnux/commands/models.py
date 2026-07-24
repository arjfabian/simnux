"""
Shared execution context injected into all SIMNUX commands.

Provides controlled access to session state and the virtual filesystem.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from simnux.filesystem.vfs import SNXFileSystem
from simnux.sessions.runtime import SNXSession


if TYPE_CHECKING:
    from simnux.commands.dispatcher import CommandDispatcher


@dataclass
class CommandContext:
    """Per-session injection container for command execution.

    Contains references to the mutable session state and filesystem;
    commands share the same context object for their lifetime.
    """

    session: SNXSession
    filesystem: SNXFileSystem
    dispatcher: CommandDispatcher | None = None
