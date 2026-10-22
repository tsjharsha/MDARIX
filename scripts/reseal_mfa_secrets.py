"""Re-seal every stored authenticator secret with the current MFA encryption key (after a key rotation).

Opens each sealed secret (an account's authenticator, and one being set up) with the keyring (MDARIX_MFA_ENCRYPTION_KEY
plus MDARIX_MFA_ENCRYPTION_KEYS, auth/totp.py) and seals it again with the current key and key ID. The new value must
open with the current key alone and give the same secret before it replaces the old one. Secrets already on the current
key are left alone. A secret that cannot be opened is reported (the account, never the secret) and left unchanged, and
the script then exits 1. Dry run by default; safe to run again.

    python scripts/reseal_mfa_secrets.py            # what would change
    python scripts/reseal_mfa_secrets.py --apply    # then remove the old key from MDARIX_MFA_ENCRYPTION_KEYS
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from auth import totp  # noqa: E402
from backend.app.db.models.foundation import AuthUser  # noqa: E402
from backend.app.db.session import SessionLocal  # noqa: E402
from backend.app.db.tenant_scope import bind_system  # noqa: E402

COLUMNS = ("mfa_secret_encrypted", "mfa_pending_secret_encrypted")


def on_current_key(token: str, user_id: str, ring, current_only) -> bool:
    """Sealed with the current key ID; or, while the key has no ID, sealed without one and opened by the current key."""
    key_id = totp.sealed_key_id(token)
    if ring.current_id is not None:
        return key_id == ring.current_id
    if key_id is not None:
        return False
    try:
        totp.decrypt_secret(token, user_id, current_only)
        return True
    except ValueError:
        return False


def reseal(db, *, apply: bool, user_ids=None, out=print) -> dict[str, int]:
    """Counts of secrets re-sealed (or that would be), already on the current key, and unreadable. ``user_ids`` limits
    it to those accounts (tests). The rows are locked until the caller commits, so a sign-in cannot change one meanwhile.
    """
    ring = totp.keyring()
    current_only = replace(ring, older={})
    counts = {"resealed": 0, "current": 0, "failed": 0}
    query = db.query(AuthUser).filter(
        (AuthUser.mfa_secret_encrypted.isnot(None)) | (AuthUser.mfa_pending_secret_encrypted.isnot(None))
    )
    if user_ids is not None:
        query = query.filter(AuthUser.id.in_(list(user_ids)))
    rows = query.order_by(AuthUser.id).with_for_update().all()
    for user in rows:
        for column in COLUMNS:
            token = getattr(user, column)
            if not token:
                continue
            what = f"account {user.business_id or user.id} ({'set up' if column == COLUMNS[0] else 'being set up'})"
            try:
                if on_current_key(token, str(user.id), ring, current_only):
                    counts["current"] += 1
                    continue
                secret = totp.decrypt_secret(token, str(user.id), ring)
                resealed = totp.encrypt_secret(secret, str(user.id))
                if totp.decrypt_secret(resealed, str(user.id), current_only) != secret:
                    raise ValueError("MFA_RESEAL_CHECK_FAILED")
            except Exception as exc:
                counts["failed"] += 1
                out(f"UNREADABLE  {what}: {type(exc).__name__} {exc}"[:200])
                continue
            if apply:
                setattr(user, column, resealed)
            counts["resealed"] += 1
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="write the re-sealed secrets (default: dry run)")
    args = parser.parse_args(argv)
    try:
        key_id = totp.keyring().current_id or "(no key ID)"
    except totp.MfaUnavailable as exc:
        print(f"STOP: {exc}. Nothing was changed.")
        return 1
    db = SessionLocal()
    try:
        bind_system(db, "re-seal MFA secrets")
        counts = reseal(db, apply=args.apply)
        if args.apply:
            db.commit()
        else:
            db.rollback()
    finally:
        db.close()
    verb = "Re-sealed" if args.apply else "Would re-seal"
    print(f"{verb} {counts['resealed']}; already on key {key_id}: {counts['current']}; unreadable: {counts['failed']}.")
    return 1 if counts["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
