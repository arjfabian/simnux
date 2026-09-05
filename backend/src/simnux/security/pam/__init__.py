"""Scenario-local password authentication primitives (initial SNXPAM).

``SNXPAM`` encodes and verifies password credentials without ever storing the
plaintext; the hashing mechanism contract lives in ``models`` so it can be
replaced independently.
"""

from simnux.security.pam.models import ALGORITHM
from simnux.security.pam.models import DEFAULT_ITERATIONS
from simnux.security.pam.models import PasswordHasher
from simnux.security.pam.models import SNXPasswordCredential
from simnux.security.pam.runtime import SNXPAM


__all__ = [
    "ALGORITHM",
    "DEFAULT_ITERATIONS",
    "PasswordHasher",
    "SNXPAM",
    "SNXPasswordCredential",
]
