"""Benchmark tenant data-plane indexing and retrieval.

Usage:
  python scripts/benchmark_tenant_retrieval.py --tenant-id <UUID> --query "lot 10 delayed restart"

The tenant id is used only to resolve the approved data-plane registry record;
no database URL can be supplied by a caller. Results are internal validation
evidence, not a production capacity claim.
"""

from __future__ import annotations

import argparse
import json
import time

from backend.app.db.data_plane import session_factory
from backend.app.db.models.customer_lifecycle import TenantDataPlane
from backend.app.db.models.foundation import Evidence
from backend.app.db.session import SessionLocal
from retrieval.schemas import RetrievalRequest
from retrieval.service import TrustedRetrievalService


def run(tenant_id: str, query: str, repeats: int) -> dict:
    control = SessionLocal()
    try:
        plane = (
            control.query(TenantDataPlane)
            .filter(TenantDataPlane.tenant_id == tenant_id, TenantDataPlane.status == "ACTIVE")
            .one()
        )
        db = session_factory(plane.database_ref, plane.connection_secret_ref)()
    finally:
        control.close()
    service = TrustedRetrievalService()
    try:
        started = time.perf_counter()
        indexing = service.index_evidence_chunks(db, tenant_id)
        indexing_ms = round((time.perf_counter() - started) * 1000, 2)
        latencies = []
        responses = []
        for _ in range(repeats):
            started = time.perf_counter()
            response = service.retrieve(
                db, RetrievalRequest(tenant_id=tenant_id, query_text=query, retrieval_mode="hybrid")
            )
            latencies.append(round((time.perf_counter() - started) * 1000, 2))
            responses.append(response)
        result_ids = {result.evidence_id for response in responses for result in response.results}
        owned_ids = (
            {
                row.id
                for row in db.query(Evidence.id)
                .filter(Evidence.tenant_id == tenant_id, Evidence.id.in_(result_ids))
                .all()
            }
            if result_ids
            else set()
        )
        return {
            "tenant_id": tenant_id,
            "database_ref": plane.database_ref,
            "indexing": indexing,
            "indexing_ms": indexing_ms,
            "query_repeats": repeats,
            "query_latency_ms": {
                "min": min(latencies),
                "max": max(latencies),
                "avg": round(sum(latencies) / len(latencies), 2),
            },
            "result_counts": [item.results_count for item in responses],
            "tenant_scope_enforced": owned_ids == result_ids,
            "limitations": ["Synthetic validation only; not a production capacity or SLA claim."],
        }
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--query", required=True)
    parser.add_argument("--repeats", type=int, default=10)
    args = parser.parse_args()
    print(json.dumps(run(args.tenant_id, args.query, max(1, args.repeats)), indent=2, default=str))
