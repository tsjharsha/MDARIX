"""Read a customer system through a connector and import what it returns: on request ("Sync now") or on a schedule.

``fetch_provider_records`` reads the connector's endpoint page by page: it follows ``next`` (an address on the same
host as the endpoint) or ``next_cursor`` (sent back as ``cursor=``), up to ``max_pages`` pages and
``MDARIX_CONNECTOR_MAX_BYTES`` in total (5 MB per page). Timeouts, 5xx answers and rate limits (429) are retried
twice with a short back-off; any other refusal stops the read. Every address passes the same outbound checks as
before (no private destinations, no redirects).

``sync_connector`` imports the records through the released mapping (all or nothing), queues one outbox event per
record carrying its identity and fingerprint only, records the run for Sync activity and Reconciliation, and audits
it. The scheduler (``run_scheduled_syncs``) syncs connections that set ``sync_every_minutes`` (at least 15).
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin, urlparse
from urllib.request import Request as UrlRequest

from sqlalchemy.orm import Session

from backend.app.access.common import _connector_credential, _safe_provider_url
from backend.app.access.outbound import safe_urlopen
from backend.app.db.models.enterprise import ConnectorRun
from backend.app.db.models.foundation import ConnectorConfiguration
from backend.app.db.models.stage2 import OutboxEvent

logger = logging.getLogger("mdarix.connector_sync")

PAGE_BYTES = 5_000_000
DEFAULT_MAX_PAGES = 50
RETRIES = 2
MIN_SCHEDULE_MINUTES = 15


class ProviderReadError(RuntimeError):
    def __init__(self, code: str, status: int = 502, message: str = "Provider read failed"):
        super().__init__(code)
        self.code, self.status, self.message = code, status, message


def _max_total_bytes() -> int:
    raw = os.getenv("MDARIX_CONNECTOR_MAX_BYTES", "").strip()
    return int(raw) if raw.isdigit() else 50_000_000


def _get_json(url: str, headers: dict, timeout: float) -> tuple[dict, int]:
    """One page, with retries for timeouts, 5xx and 429 (Retry-After honoured up to 10 seconds)."""
    last: Exception | None = None
    for attempt in range(RETRIES + 1):
        try:
            with safe_urlopen(UrlRequest(url, headers=headers, method="GET"), timeout=timeout) as response:
                raw = response.read(PAGE_BYTES + 1)
            if len(raw) > PAGE_BYTES:
                raise ProviderReadError("PROVIDER_RESPONSE_TOO_LARGE", message="A provider page exceeds 5 MB")
            return json.loads(raw.decode()), len(raw)
        except HTTPError as exc:
            last = exc
            if exc.code != 429 and exc.code < 500:
                break
            try:
                wait = min(float(exc.headers.get("retry-after") or 0), 10.0)
            except (TypeError, ValueError):
                wait = 0.0
            if attempt < RETRIES:
                time.sleep(max(wait, 2**attempt))
        except (URLError, TimeoutError) as exc:
            last = exc
            if attempt < RETRIES:
                time.sleep(2**attempt)
        except ValueError as exc:  # not JSON
            raise ProviderReadError("PROVIDER_READ_FAILED") from exc
    raise ProviderReadError("PROVIDER_READ_FAILED") from last


def fetch_provider_records(row: ConnectorConfiguration, source_system: str) -> list:
    configuration = row.configuration or {}
    source_object = configuration.get("source_object", source_system)
    timeout = float(configuration.get("timeout_seconds", 10))
    max_pages = int(configuration.get("max_pages", DEFAULT_MAX_PAGES))
    try:
        url = _safe_provider_url(
            configuration["endpoint"], configuration.get("records_path", f"records/{source_object}"), timeout=timeout
        )
        token = _connector_credential(configuration, row)
    except ValueError as exc:
        raise ProviderReadError(str(exc), 422, "Connector endpoint configuration is not safe or valid") from exc
    tenant_key = configuration.get("tenant_key")
    if tenant_key:
        url += ("&" if "?" in url else "?") + f"tenant={tenant_key}"
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
        headers["X-Provider-Token"] = token
    base = urlparse(url)
    records: list = []
    total = 0
    for _page in range(max_pages):
        body, size = _get_json(url, headers, timeout)
        total += size
        if total > _max_total_bytes():
            raise ProviderReadError("PROVIDER_RESPONSE_TOO_LARGE", message="The provider returned more than allowed")
        if tenant_key and body.get("tenant_key") != tenant_key:
            raise ProviderReadError(
                "PROVIDER_TENANT_SCOPE_INVALID", message="Provider returned an unexpected tenant scope"
            )
        page = body.get("records", [])
        if not isinstance(page, list):
            raise ProviderReadError("PROVIDER_READ_FAILED")
        records.extend(page)
        following = body.get("next")
        cursor = body.get("next_cursor")
        if following:
            candidate = urlparse(urljoin(url, str(following)))
            # Only further pages of the same service: a "next" link can never send the request elsewhere.
            if (candidate.scheme, candidate.netloc) != (base.scheme, base.netloc):
                raise ProviderReadError("PROVIDER_NEXT_LINK_REFUSED", message="Provider paging left its own host")
            url = candidate.geturl()
        elif cursor:
            url = f"{base.scheme}://{base.netloc}{base.path}?" + urlencode(
                {**({"tenant": tenant_key} if tenant_key else {}), "cursor": str(cursor)}
            )
        else:
            return records
    raise ProviderReadError("PROVIDER_TOO_MANY_PAGES", message=f"More than {max_pages} pages; raise max_pages")


def sync_connector(
    db: Session,
    tenant_id,
    row: ConnectorConfiguration,
    source_system: str,
    actor_ref: str,
    *,
    records: list | None = None,
    run_type: str = "MANUAL",
) -> dict:
    """Read (unless ``records`` were supplied), import and record one sync. Commits; returns the outcome."""
    from backend.app.access.connector_mapping import MappingNotUsable, import_connector_records, released_mapping
    from backend.app.access.configuration import _record_sync
    from backend.app.db.data_plane import open_tenant_data_session
    from backend.app.enterprise_audit import make_audit_event
    from integration.api_contract import idempotency_key
    from integration.gateway import ConnectionConfig, Connector

    if not records and (row.configuration or {}).get("endpoint"):
        records = fetch_provider_records(row, source_system)
    connector = Connector(
        ConnectionConfig(str(tenant_id), str(row.id), row.code, row.connector_type, source_system), records or []
    )
    result = connector.read_records()
    canonical_import = None
    mapping_code = (row.configuration or {}).get("mapping_code")
    if mapping_code and result:
        try:
            mapping = released_mapping(db, tenant_id, str(mapping_code))
        except MappingNotUsable as exc:
            canonical_import = {"status": "BLOCKED", "reason": str(exc)}
        else:
            with open_tenant_data_session(tenant_id) as data:
                try:
                    canonical_import = import_connector_records(data, tenant_id, row.code, mapping, result)
                except MappingNotUsable as exc:
                    canonical_import = {"status": "BLOCKED", "reason": str(exc)}
                if canonical_import.get("status") == "IMPORTED":
                    data.commit()
                else:
                    data.rollback()
    now = datetime.now(timezone.utc)
    for record in result:
        # The control database's outbox is only the delivery ledger: it carries the record's identity and fingerprint,
        # never its content, which belongs in the tenant's data plane (scripts/run_outbox_worker.py).
        external_id = str(record.get("external_id") or record.get("id") or "") if isinstance(record, dict) else ""
        version = record.get("record_version") or record.get("version") if isinstance(record, dict) else None
        db.add(
            OutboxEvent(
                tenant_id=tenant_id,
                event_name="PROVIDER_RECORD_RECEIVED",
                aggregate_type=f"{row.code}:{source_system}",
                payload={
                    "tenant_id": str(tenant_id),
                    "source_system": source_system,
                    "external_id": external_id,
                    "record_version": str(version) if version is not None else None,
                    "idempotency_key": idempotency_key(str(tenant_id), source_system, "Record", record),
                },
                occurred_at=now,
            )
        )
    run = _record_sync(tenant_id, row, source_system, len(result), canonical_import)
    run.run_type = run_type
    db.add(run)
    db.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=actor_ref,
            action="CONNECTOR_EXECUTED",
            entity_type="ConnectorConfiguration",
            entity_id=row.id,
            details={"version": row.version, "run_type": run_type, "records_read": len(result)},
        )
    )
    db.commit()
    return {"run": run, "records_read": len(result), "canonical_import": canonical_import}


def record_failed_run(
    db: Session, tenant_id, row: ConnectorConfiguration, source_system: str, code: str, run_type: str
):
    now = datetime.now(timezone.utc)
    db.add(
        ConnectorRun(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            connection_id=row.code,
            source_system=(row.configuration or {}).get("source_object") or source_system or row.connector_type,
            run_type=run_type,
            status="FAILED",
            records_received=0,
            records_accepted=0,
            records_rejected=0,
            failure_category=code[:80],
            started_at=now,
            completed_at=now,
            created_at=now,
        )
    )
    db.commit()


def run_scheduled_syncs(db: Session, now: datetime | None = None) -> dict:
    """Sync every active connection whose ``sync_every_minutes`` has passed since its last run (scheduler)."""
    from backend.app.db.tenant_scope import bind_system

    now = now or datetime.now(timezone.utc)
    synced, failed = 0, []
    rows = db.query(ConnectorConfiguration).filter(ConnectorConfiguration.status == "ACTIVE").all()
    for row in rows:
        configuration = row.configuration or {}
        try:
            every = int(configuration.get("sync_every_minutes") or 0)
        except (TypeError, ValueError):
            every = 0
        if every < MIN_SCHEDULE_MINUTES or not configuration.get("endpoint"):
            continue
        last = (
            db.query(ConnectorRun.started_at)
            .filter(ConnectorRun.tenant_id == row.tenant_id, ConnectorRun.connection_id == row.code)
            .order_by(ConnectorRun.started_at.desc())
            .first()
        )
        if last and last[0] and now - last[0] < timedelta(minutes=every):
            continue
        source = configuration.get("source_object") or row.connector_type
        try:
            sync_connector(db, row.tenant_id, row, source, "system:scheduler", run_type="SCHEDULED")
            synced += 1
        except ProviderReadError as exc:
            db.rollback()
            bind_system(db, "scheduled connector sync: record the failure")
            record_failed_run(db, row.tenant_id, row, source, exc.code, "SCHEDULED")
            failed.append({"tenant_id": str(row.tenant_id), "connection": row.code, "error": exc.code})
            logger.warning("Scheduled sync of %s failed: %s", row.code, exc.code)
        bind_system(db, "scheduled connector syncs")
    return {"synced": synced, "failed": failed}
