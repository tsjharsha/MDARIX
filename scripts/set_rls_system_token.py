"""Store the hash of MDARIX_RLS_SYSTEM_TOKEN in the database (owner credentials), so the API can enter system scope.

Run once when deploying a new environment, and again whenever the token is rotated (then restart the API so it uses
the new token). The database keeps only the SHA-256 of the token, in a table the application role cannot read.

    MDARIX_RLS_SYSTEM_TOKEN=<random 48+ characters> python scripts/set_rls_system_token.py
"""

from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402


def main() -> int:
    token = os.getenv("MDARIX_RLS_SYSTEM_TOKEN", "").strip()
    if len(token) < 32:
        print("MDARIX_RLS_SYSTEM_TOKEN must be set to a random value of at least 32 characters.", file=sys.stderr)
        return 2
    from backend.app.db.session import engine

    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO public.mdarix_rls_secret (id, token_hash, updated_at) VALUES (1, :digest, now()) "
                "ON CONFLICT (id) DO UPDATE SET token_hash = excluded.token_hash, updated_at = now()"
            ),
            {"digest": digest},
        )
    print("System-scope token stored. Restart the API and worker so they use it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
