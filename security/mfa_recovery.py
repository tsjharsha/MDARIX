"""Local MVP MFA recovery-code lifecycle primitives."""
import hashlib
import secrets


def issue_recovery_codes(count: int = 8) -> list[str]:
    if count < 1 or count > 20:
        raise ValueError("recovery code count must be between 1 and 20")
    return [f"{secrets.token_hex(4)}-{secrets.token_hex(4)}" for _ in range(count)]


def hash_recovery_codes(codes: list[str]) -> list[str]:
    return [hashlib.sha256(code.encode("utf-8")).hexdigest() for code in codes]


def consume_recovery_code(code: str, hashes: list[str]) -> tuple[bool, list[str]]:
    digest = hashlib.sha256(code.encode("utf-8")).hexdigest()
    if digest not in hashes:
        return False, hashes
    remaining = list(hashes)
    remaining.remove(digest)
    return True, remaining
