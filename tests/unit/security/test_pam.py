"""Unit tests for the initial SNXPAM password credential module.

Covers credential encoding, absence of the plaintext in stored credentials,
verification success/failure, salted non-identity of equal passwords, and
safe handling of malformed stored credentials.
"""

import pytest

from simnux.security.pam import SNXPAM
from simnux.security.pam import SNXPasswordCredential


FAST_ITERATIONS = 2_000


def make_pam() -> SNXPAM:
    """Return an SNXPAM with a small iteration count to keep tests fast."""
    return SNXPAM(iterations=FAST_ITERATIONS)


class TestEncode:
    """Password -> stored credential encoding."""

    def test_encode_returns_credential(self):
        """Encoding a plaintext produces a populated stored credential."""
        credential = make_pam().encode("s3cr3t-pw")

        assert isinstance(credential, SNXPasswordCredential)
        assert credential.algorithm == SNXPAM.ALGORITHM
        assert credential.iterations == FAST_ITERATIONS
        assert credential.salt
        assert credential.password_hash

    def test_credential_does_not_contain_plaintext(self):
        """The stored credential never keeps the plaintext password."""
        credential = make_pam().encode("s3cr3t-pw")

        assert "s3cr3t-pw" not in credential.salt
        assert "s3cr3t-pw" not in credential.password_hash
        assert "s3cr3t-pw" not in repr(credential)

    def test_encode_with_explicit_salt_is_deterministic(self):
        """Supplying a salt yields a reproducible credential for the password."""
        pam = make_pam()

        first = pam.encode("same-pw", salt=b"fixed-salt-16-bytes.")
        second = pam.encode("same-pw", salt=b"fixed-salt-16-bytes.")

        assert first == second

    def test_two_encodes_of_same_password_differ(self):
        """Random salts make equal plaintexts produce distinct credentials."""
        pam = make_pam()

        first = pam.encode("same-pw")
        second = pam.encode("same-pw")

        assert first != second
        assert first.salt != second.salt
        assert first.password_hash != second.password_hash


class TestVerify:
    """Plaintext -> stored credential verification."""

    def test_correct_password_verifies(self):
        """The matching plaintext verifies successfully."""
        pam = make_pam()
        credential = pam.encode("correct horse battery staple")

        assert pam.verify("correct horse battery staple", credential) is True

    def test_incorrect_password_fails(self):
        """A wrong plaintext does not verify."""
        pam = make_pam()
        credential = pam.encode("correct horse battery staple")

        assert pam.verify("wrong password", credential) is False

    def test_verify_respects_credential_iterations(self):
        """Verification uses the credential's own iteration count."""
        credential = make_pam().encode("pw")
        default_pam = SNXPAM()

        assert default_pam.verify("pw", credential) is True

    def test_default_iterations_roundtrip(self):
        """The default-iteration instance encodes and verifies correctly."""
        pam = SNXPAM()
        credential = pam.encode("pw")

        assert pam.verify("pw", credential) is True

    def test_tampered_hash_fails(self):
        """A credential whose stored hash was altered no longer verifies."""
        pam = make_pam()
        credential = pam.encode("pw")
        tampered = SNXPasswordCredential(
            algorithm=credential.algorithm,
            iterations=credential.iterations,
            salt=credential.salt,
            password_hash=credential.password_hash[:-1]
            + ("0" if credential.password_hash[-1] != "0" else "1"),
        )

        assert pam.verify("pw", tampered) is False


class TestMalformedCredentials:
    """Safe handling of malformed/invalid stored credentials."""

    @pytest.mark.parametrize(
        ("credential", "scenario"),
        [
            (
                SNXPasswordCredential(algorithm="md5", salt="ab", password_hash="cd"),
                "unknown algorithm",
            ),
            (SNXPasswordCredential(salt="zz", password_hash="abcd"), "non-hex salt"),
            (SNXPasswordCredential(salt="abcd", password_hash="xyz1"), "non-hex hash"),
            (SNXPasswordCredential(salt="", password_hash="abcd"), "empty salt"),
            (SNXPasswordCredential(salt="abcd", password_hash=""), "empty hash"),
            (
                SNXPasswordCredential(iterations=0, salt="abcd", password_hash="abcd"),
                "zero iterations",
            ),
            (
                SNXPasswordCredential(iterations=-5, salt="abcd", password_hash="abcd"),
                "negative iterations",
            ),
            (
                SNXPasswordCredential(salt="abc", password_hash="def"),
                "odd-length hex fields",
            ),
        ],
    )
    def test_verify_fails_safely(self, credential, scenario):
        """Malformed credentials return False instead of raising."""
        pam = make_pam()

        result = pam.verify("whatever", credential)

        assert result is False, scenario

    def test_verify_never_raises_on_garbage(self):
        """Garbage plaintexts and credentials never raise unexpected exceptions."""
        pam = make_pam()
        valid = pam.encode("pw")
        malformed = [
            SNXPasswordCredential(salt="nope", password_hash="also-not-hex"),
            SNXPasswordCredential(algorithm="argon2", salt="abcd", password_hash="ef01"),
        ]

        for credential in [valid, *malformed]:
            for plaintext in ["", "pw", "a" * 1_000, "\x00\xff", "s3cr3t"]:
                assert isinstance(pam.verify(plaintext, credential), bool)
