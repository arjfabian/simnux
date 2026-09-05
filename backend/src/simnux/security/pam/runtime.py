"""SNXPAM — development-grade password credential runtime.

Implements a deliberately simple, one-way, salted password encoding/verification
scheme suitable for development and testing. It is NOT Linux PAM and NOT a
production-grade password-hashing algorithm: no PAM configuration, no shadow
files, and no module stacking yet. The hashing mechanism obeys the essential
one-way model — plaintext is never stored, and verification recomputes the
digest from the supplied plaintext.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

from simnux.security.pam.models import ALGORITHM
from simnux.security.pam.models import DEFAULT_ITERATIONS
from simnux.security.pam.models import SNXPasswordCredential


class SNXPAM:
    """Encoding/verification service for scenario-local password credentials.

    Self-contained (stdlib only) so it can be reused by future runtime
    authentication flows and by the scenario bootstrap process. The stored
    credential is a salted PBKDF2-HMAC-SHA256 digest (hex-encoded).
    Verification uses constant-time comparison and returns ``False`` for
    malformed credentials instead of raising.
    """

    ALGORITHM = ALGORITHM
    DEFAULT_ITERATIONS = DEFAULT_ITERATIONS
    SALT_BYTES = 16

    def __init__(self, iterations: int = DEFAULT_ITERATIONS) -> None:
        """Create a PAM service; *iterations* lowers the PBKDF2 cost (testing)."""
        if iterations <= 0:
            raise ValueError("iterations must be greater than zero")
        self.iterations = iterations

    def encode(self, plaintext: str, salt: bytes | None = None) -> SNXPasswordCredential:
        """Create a stored credential for *plaintext*.

        A random salt is generated unless one is supplied explicitly. Only the
        salted digest survives; the plaintext password is never stored.
        """
        salt_bytes = salt if salt is not None else secrets.token_bytes(self.SALT_BYTES)
        if not salt_bytes:
            raise ValueError("salt must not be empty")

        digest = hashlib.pbkdf2_hmac(
            "sha256",
            plaintext.encode("utf-8"),
            salt_bytes,
            self.iterations,
        )
        return SNXPasswordCredential(
            algorithm=self.ALGORITHM,
            iterations=self.iterations,
            salt=salt_bytes.hex(),
            password_hash=digest.hex(),
        )

    def verify(self, plaintext: str, credential: SNXPasswordCredential) -> bool:
        """Verify *plaintext* against *credential*.

        Recomputes the digest with the credential's own salt and iteration
        count, then compares in constant time. Unknown algorithms and
        malformed or empty hex fields evaluate to ``False`` rather than
        raising.
        """
        if credential.algorithm != self.ALGORITHM:
            return False
        if not isinstance(credential.iterations, int) or credential.iterations <= 0:
            return False

        try:
            salt = bytes.fromhex(credential.salt)
            expected = bytes.fromhex(credential.password_hash)
        except ValueError:
            return False
        if not salt or not expected:
            return False

        actual = hashlib.pbkdf2_hmac(
            "sha256",
            plaintext.encode("utf-8"),
            salt,
            credential.iterations,
        )
        return hmac.compare_digest(actual, expected)
