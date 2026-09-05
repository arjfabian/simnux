"""PAM credential value types and the hashing-mechanism contract.

Keeps the stored credential and the encode/verify protocol separate from
``SNXPAM`` so the runtime depends only on these minimal shapes and the
hashing mechanism can be swapped without touching the runtime.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


ALGORITHM = "pbkdf2-sha256"
DEFAULT_ITERATIONS = 100_000


@dataclass(frozen=True)
class SNXPasswordCredential:
    """Stored password credential; never contains the plaintext password.

    ``salt`` and ``password_hash`` are hex-encoded so a credential
    serialises directly into scenario YAML or configuration without a
    separate codec layer. ``iterations`` travels with the credential so
    verification stays correct even if the runtime default changes later.
    """

    algorithm: str = ALGORITHM
    iterations: int = DEFAULT_ITERATIONS
    salt: str = ""
    password_hash: str = ""


class PasswordHasher(Protocol):
    """Encode/verify contract kept separate from the PAM runtime."""

    def encode(self, plaintext: str, salt: bytes | None = None) -> SNXPasswordCredential:
        """Create a stored credential for *plaintext*; *salt* defaults to random."""

    def verify(self, plaintext: str, credential: SNXPasswordCredential) -> bool:
        """Return whether *plaintext* matches the stored *credential*."""
