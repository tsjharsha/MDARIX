"""Score MDARIX's local evidence search against a versioned dataset (evaluation/retrieval/local_retrieval_v1.json).

Quality only (are the right records found, does the search abstain when none answers); governance (who may search,
what reaches a model) is tested apart (tests/test_local_retrieval_evaluation.py). The result names every version it
depends on, so a score is never read without the dataset, model and configuration it came from.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

DATASET = Path(__file__).resolve().parent / "retrieval" / "local_retrieval_v1.json"


def load_dataset(path: Path = DATASET) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def evaluate(db: Session, tenant_id: uuid.UUID, dataset: dict[str, Any], service) -> dict[str, Any]:
    """Run every question through ``service`` (a TrustedRetrievalService) and score it against the dataset."""
    from backend.app.db.models.retrieval_intelligence import RETRIEVAL_CONFIG_VERSION
    from retrieval.schemas import RetrievalRequest
    from retrieval.service import RELEVANCE_FLOOR

    top_k = int(dataset["top_k"])

    def ask(question: str):
        request = RetrievalRequest(
            tenant_id=tenant_id, query_text=question, retrieval_mode=dataset["retrieval_mode"], top_k=top_k
        )
        return service.retrieve(db, request)

    rows, hits, reciprocal, answered = [], 0, 0.0, 0
    for item in dataset["queries"]:
        response = ask(item["question"])
        found = [result.evidence_identifier for result in response.results]
        rank = next((position for position, ev in enumerate(found, 1) if ev in item["relevant"]), None)
        hits += rank is not None
        reciprocal += 1 / rank if rank else 0.0
        answered += response.status == "COMPLETED"
        rows.append({"id": item["id"], "status": response.status, "rank": rank, "found": found})
    abstained = 0
    for item in dataset["unrelated"]:
        response = ask(item["question"])
        abstained += response.status != "COMPLETED"
        rows.append({"id": item["id"], "status": response.status, "found": []})
    metadata = service.embedding_provider.model_metadata()
    count = len(dataset["queries"])
    return {
        "versions": {
            "dataset": f"{dataset['dataset']}@{dataset['version']}",
            "embedding_model": metadata.model,
            "embedding_model_version": metadata.model_version,
            "embedding_pipeline_version": metadata.pipeline_version,
            "retrieval_config_version": RETRIEVAL_CONFIG_VERSION,
            "relevance_floor": RELEVANCE_FLOOR.get(metadata.model),
        },
        "metrics": {
            "recall_at_k": hits / count,
            "mean_reciprocal_rank": reciprocal / count,
            "answered_when_relevant": answered / count,
            "abstained_when_unrelated": abstained / len(dataset["unrelated"]),
        },
        "rows": rows,
    }
