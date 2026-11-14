"""Count the rows that would stop migration tr22 (DB-1): references to another organization's row, and product
versions that are not a version of the record's product. Read only; prints counts, never row contents.

Run it against a copy of a production backup before a release with tr22/tr23, as the owner (the system scope is
used, so every organization's rows are counted):

    python scripts/check_tenant_references.py

Exit code 0 when every count is zero, 1 otherwise.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.db.session import engine  # noqa: E402
from backend.app.db.tenant_scope import bind_connection_system  # noqa: E402
from infrastructure.database.migrations.tenant_references import refusal, violation_counts  # noqa: E402


def main() -> int:
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.exec_driver_sql("SET TRANSACTION READ ONLY")
            bind_connection_system(connection)
            counts = violation_counts(connection)
        finally:
            transaction.rollback()
    for label, count in counts:
        print(f"{count:>8}  {label}")
    message = refusal(counts)
    print(message or f"All {len(counts)} checks are zero.")
    return 1 if message else 0


if __name__ == "__main__":
    sys.exit(main())
