"""Security helpers for password hashing and verification."""

from __future__ import annotations

import hashlib
import hmac
import secrets

PBKDF2_ITERATIONS = 390000


def hash_password(password: str) -> str:
    """Return a PBKDF2 hash in the format: pbkdf2_sha256$iters$salt$hash."""
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PBKDF2_ITERATIONS,
    )
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, encoded_hash: str) -> bool:
    """Verify a plaintext password against stored PBKDF2 hash."""
    try:
        algorithm, iterations, salt, expected_hex = encoded_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            int(iterations),
        )
        return hmac.compare_digest(digest.hex(), expected_hex)
    except (ValueError, TypeError):
        return False
