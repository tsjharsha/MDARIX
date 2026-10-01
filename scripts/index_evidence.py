"""Chunk and embed evidence with the local language model, for one tenant or every tenant whose data is here.

    python scripts/index_evidence.py --tenant ACME_CARE_SYNTHETIC
    python scripts/index_evidence.py --all [--reprocess]

Uses MDARIX_EMBEDDING_PROVIDER (default "local"). Safe to rerun: chunks and vectors already made are kept.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.db.models.foundation import Evidence, Tenant  # noqa: E402
from backend.app.db.session import SessionLocal  # noqa: E402
from retrieval.indexing import index_tenant_evidence  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--tenant", help="tenant key")
    target.add_argument("--all", action="store_true", help="every tenant with evidence in this database")
    parser.add_argument("--reprocess", action="store_true", help="re-embed chunks that are already indexed")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        query = db.query(Tenant)
        if args.tenant:
            query = query.filter(Tenant.tenant_key == args.tenant)
        else:
            query = query.filter(Tenant.id.in_(db.query(Evidence.tenant_id).distinct()))
        tenants = query.order_by(Tenant.tenant_key).all()
        if not tenants:
            print("No matching tenant.", file=sys.stderr)
            return 1
        for tenant in tenants:
            result = index_tenant_evidence(db, tenant.id, reprocess=args.reprocess)
            print(json.dumps({"tenant": tenant.tenant_key, **result}))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
