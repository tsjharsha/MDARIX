"""MFA recovery codes: issued once, stored only as SHA-256 hashes, each usable once.

A code is 64 random bits written as two groups of eight hex digits (xxxxxxxx-xxxxxxxx); hashing it without a salt is
enough, because the code itself is random and cannot be guessed from a dictionary. A code is compared with every
stored hash in constant time, so how long a check takes does not tell which hashes are near a match.
"""

import hashlib
import hmac
import secrets


def issue_recovery_codes(count: int = 8) -> list[str]:
    if count < 1 or count > 20:
        raise ValueError("recovery code count must be between 1 and 20")
    return [f"{secrets.token_hex(4)}-{secrets.token_hex(4)}" for _ in range(count)]


def hash_recovery_codes(codes: list[str]) -> list[str]:
    return [hashlib.sha256(code.encode("utf-8")).hexdigest() for code in codes]


def consume_recovery_code(code: str, hashes: list[str]) -> tuple[bool, list[str]]:
    digest = hashlib.sha256(code.encode("utf-8")).hexdigest()
    match = None
    for index, stored in enumerate(hashes):
        # Every stored hash is compared, found or not.
        if hmac.compare_digest(digest, str(stored)) and match is None:
            match = index
    if match is None:
        return False, hashes
    remaining = list(hashes)
    del remaining[match]
    return True, remaining
