"""Re-seal every stored connector API key with the current connector encryption key (after a key rotation).

Opens each sealed key with the keyring (MDARIX_CONNECTOR_ENCRYPTION_KEY plus MDARIX_CONNECTOR_ENCRYPTION_KEYS) and
seals it again with the current key and key ID. Keys already sealed with the current key ID are left alone. A key
that cannot be opened is reported and left unchanged. Dry run by default.

    python scripts/reseal_connector_keys.py            # what would change
    python scripts/reseal_connector_keys.py --apply    # then remove the old key from MDARIX_CONNECTOR_ENCRYPTION_KEYS
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from access_control.connector_secrets import current_key, open_sealed, seal, sealed_key_id  # noqa: E402
from backend.app.db.models.foundation import ConnectorConfiguration  # noqa: E402
from backend.app.db.session import SessionLocal  # noqa: E402
from backend.app.db.tenant_scope import bind_system  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="write the re-sealed keys (default: dry run)")
    args = parser.parse_args()
    key_id, _ = current_key()
    db = SessionLocal()
    resealed = current = failed = 0
    try:
        bind_system(db, "re-seal connector keys")
        rows = db.query(ConnectorConfiguration).filter(ConnectorConfiguration.credential_encrypted.isnot(None)).all()
        for row in rows:
            if sealed_key_id(row.credential_encrypted) == key_id:
                current += 1
                continue
            try:
                plain = open_sealed(row.credential_encrypted, row.tenant_id, row.id)
            except Exception as exc:
                failed += 1
                print(f"UNREADABLE  connector {row.id} (tenant {row.tenant_id}): {type(exc).__name__}")
                continue
            if args.apply:
                row.credential_encrypted = seal(plain, row.tenant_id, row.id)
            resealed += 1
        if args.apply:
            db.commit()
    finally:
        db.close()
    verb = "Re-sealed" if args.apply else "Would re-seal"
    print(f"{verb} {resealed}; already on key {key_id}: {current}; unreadable: {failed}.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
