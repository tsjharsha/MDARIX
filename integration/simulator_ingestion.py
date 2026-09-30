"""Tenant-safe reads from provider simulators into the MDARIX outbox.

The module deliberately separates provider transport from MDARIX persistence:
provider records are never inserted directly into business tables. Each read is
represented by an idempotent outbox event for the normal ingestion pipeline.
"""

import json
import uuid
from urllib.request import Request, urlopen
from uuid import UUID

from sqlalchemy.orm import Session

from backend.app.db.models.enterprise import ConnectorRun, ConnectorSourceRecord
from backend.app.db.models.stage2 import OutboxEvent
from integration.api_contract import idempotency_key
from integration.api_contract import fetch_page
from source_simulator.provider_catalog import PROVIDER_PORTS


def read_provider(provider: str, tenant_key: str, token: str, entity: str, host: str = "127.0.0.1") -> list[dict]:
    provider = provider.upper()
    url = f"http://{host}:{PROVIDER_PORTS[provider]}/records/{entity}?tenant={tenant_key}"
    request = Request(url, headers={"X-Provider-Token": token, "Accept": "application/json"})
    with urlopen(request, timeout=10) as response:
        body = json.loads(response.read().decode())
    if body.get("tenant_key") != tenant_key:
        raise ValueError("provider returned an unexpected tenant scope")
    return body.get("records", [])


def provider_endpoint(provider: str, host: str = "127.0.0.1") -> str:
    """Return the local simulator endpoint for any registered provider family."""
    key = provider.upper()
    if key not in PROVIDER_PORTS:
        raise ValueError(f"UNKNOWN_PROVIDER:{key}")
    return f"http://{host}:{PROVIDER_PORTS[key]}"


def read_provider_page(
    provider: str,
    tenant_key: str,
    token: str,
    entity: str,
    *,
    cursor: str | None = None,
    since: str | None = None,
    limit: int = 100,
    host: str = "127.0.0.1",
) -> dict:
    """Read one bounded, retryable provider page using the shared contract."""
    endpoint = provider_endpoint(provider, host)
    page = fetch_page(
        endpoint,
        f"records/{entity}",
        headers={"X-Provider-Token": token},
        limit=limit,
        cursor=cursor,
        since=since,
    )
    if page.get("tenant_key") != tenant_key:
        raise ValueError("PROVIDER_TENANT_SCOPE_MISMATCH")
    return page


def read_provider_schema(provider: str, tenant_key: str, token: str, entity: str, *, host: str = "127.0.0.1") -> dict:
    """Read and tenant-validate a provider schema before ingestion."""
    endpoint = provider_endpoint(provider, host)
    page = fetch_page(
        endpoint,
        f"schema/{entity}",
        headers={"X-Provider-Token": token},
        limit=1,
    )
    if page.get("tenant_key") != tenant_key:
        raise ValueError("PROVIDER_TENANT_SCOPE_MISMATCH")
    return page


def enqueue_provider_records(
    db: Session, tenant_id: UUID, provider: str, tenant_key: str, entity: str, records: list[dict]
) -> int:
    created = 0
    for record in records:
        external_id = str(record.get("external_id", ""))
        fingerprint = idempotency_key(str(tenant_id), provider, entity, record)
        event_name = "PROVIDER_RECORD_RECEIVED"
        duplicate = (
            db.query(OutboxEvent)
            .filter(
                OutboxEvent.tenant_id == tenant_id,
                OutboxEvent.event_name == event_name,
                OutboxEvent.aggregate_type == f"{provider}:{entity}",
                OutboxEvent.payload["external_id"].as_string() == external_id,
                OutboxEvent.payload["fingerprint"].as_string() == fingerprint,
            )
            .first()
        )
        if duplicate:
            continue
        db.add(
            OutboxEvent(
                tenant_id=tenant_id,
                event_name=event_name,
                aggregate_type=f"{provider}:{entity}",
                payload={
                    "tenant_key": tenant_key,
                    "provider": provider,
                    "entity": entity,
                    "external_id": external_id,
                    "fingerprint": fingerprint,
                    "record": record,
                },
                occurred_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
            )
        )
        created += 1
    return created


def persist_provider_ingestion(
    db: Session,
    tenant_id: UUID,
    connector_id: str,
    provider: str,
    entity: str,
    records: list[dict],
    *,
    schema_status: str = "MATCH",
    correlation_id: str | None = None,
    data_db: Session | None = None,
) -> dict:
    """Persist a connector run and idempotent source-record ledger.

    This is the durable boundary between an external read and MDARIX outbox
    processing.  Replays remain visible as duplicates and never create a
    second source-record identity for the same tenant/provider record.
    """
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    run = ConnectorRun(
        tenant_id=tenant_id,
        connection_id=str(connector_id),
        source_system=provider,
        run_type="INCREMENTAL",
        status="RUNNING",
        records_received=len(records),
        schema_drift_status=schema_status,
        correlation_id=correlation_id,
        started_at=now,
        created_at=now,
    )
    db.add(run)
    db.flush()
    data_run = None
    if data_db is not None:
        data_run = ConnectorRun(
            id=run.id,
            tenant_id=tenant_id,
            connection_id=str(connector_id),
            source_system=provider,
            run_type="INCREMENTAL",
            status="RUNNING",
            records_received=len(records),
            schema_drift_status=schema_status,
            correlation_id=correlation_id,
            started_at=now,
            created_at=now,
        )
        data_db.add(data_run)
        data_db.flush()
    accepted = duplicates = 0
    for record in records:
        external_id = str(record.get("external_id") or record.get("id") or "")
        version = str(record.get("record_version") or record.get("version") or "") or None
        fingerprint = idempotency_key(str(tenant_id), provider, entity, record)
        existing = (
            db.query(ConnectorSourceRecord)
            .filter(
                ConnectorSourceRecord.tenant_id == tenant_id,
                ConnectorSourceRecord.source_system == provider,
                ConnectorSourceRecord.source_record_id == external_id,
                ConnectorSourceRecord.source_record_version == version,
            )
            .first()
        )
        if existing:
            duplicates += 1
            continue
        db.add(
            ConnectorSourceRecord(
                tenant_id=tenant_id,
                connector_run_id=run.id,
                source_system=provider,
                source_record_id=external_id,
                source_record_version=version,
                fingerprint=fingerprint,
                processing_status="QUEUED",
                ingested_at=now,
                created_at=now,
            )
        )
        if data_db is not None:
            data_db.add(
                ConnectorSourceRecord(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    connector_run_id=data_run.id,
                    source_system=provider,
                    source_record_id=external_id,
                    source_record_version=version,
                    fingerprint=fingerprint,
                    processing_status="QUEUED",
                    ingested_at=now,
                    created_at=now,
                )
            )
        db.add(
            OutboxEvent(
                tenant_id=tenant_id,
                event_name="PROVIDER_RECORD_RECEIVED",
                aggregate_type=f"{provider}:{entity}",
                payload={
                    "tenant_id": str(tenant_id),
                    "provider": provider,
                    "entity": entity,
                    "tenant_key": str(tenant_id),
                    "external_id": external_id,
                    "record_version": version,
                    "idempotency_key": fingerprint,
                    "record": record,
                },
                occurred_at=now,
            )
        )
        accepted += 1
    run.records_accepted = accepted
    run.records_duplicate = duplicates
    run.status = "COMPLETED_WITH_WARNINGS" if duplicates else "COMPLETED"
    run.completed_at = datetime.now(timezone.utc)
    db.flush()
    if data_run is not None:
        data_run.records_accepted = accepted
        data_run.records_duplicate = duplicates
        data_run.status = "COMPLETED_WITH_WARNINGS" if duplicates else "COMPLETED"
        data_run.completed_at = datetime.now(timezone.utc)
        data_db.commit()
    return {
        "run_id": str(run.id),
        "status": run.status,
        "accepted": accepted,
        "duplicates": duplicates,
        "schema_status": schema_status,
    }
