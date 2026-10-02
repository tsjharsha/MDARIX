"""Production-like provider API simulator, isolated from MDARIX storage.

One process simulates one customer application (TrackWise Digital, SAP, Teamcenter, ...). Each customer of it is a
tenant with its own database and API key: MDARIX connects with that key, the way it connects to a real customer
system. Records are loaded from the CSV templates in data/source-templates (upload page at "/").
"""

import csv
import hmac
import io
import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Body, FastAPI, Header, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from source_simulator import persistent_store as store
from source_simulator.provider_catalog import PROVIDER_PORTS, schema_for

PROVIDER = os.getenv("SIMULATOR_PROVIDER", "TRACKWISE").upper()
# The original four test tenants: fixed tokens, records in the shared base database.
TOKEN_MAP = {
    token: tenant
    for tenant, token in (
        item.strip().split("=", 1)
        for item in os.getenv(
            "SIMULATOR_TENANT_TOKENS", "TENANT_A=sim-a,TENANT_B=sim-b,TENANT_C=sim-c,TENANT_D=sim-d"
        ).split(",")
        if "=" in item
    )
}
TENANTS = {"TENANT_A", "TENANT_B", "TENANT_C", "TENANT_D"}
CATALOG = json.loads((Path(__file__).parent / "source_catalog.json").read_text(encoding="utf-8"))
APPLICATION = CATALOG.get(PROVIDER, {"name": PROVIDER, "port": PROVIDER_PORTS.get(PROVIDER), "records": {}})
MAX_UPLOAD_BYTES = int(os.getenv("SIMULATOR_MAX_UPLOAD_BYTES", str(5 * 1024 * 1024)))
MAX_UPLOAD_ROWS = int(os.getenv("SIMULATOR_MAX_UPLOAD_ROWS", "20000"))

app = FastAPI(title=f"{APPLICATION['name']} simulator", version="2.0")


def tenant_from_token(token: str | None, requested: str | None) -> tuple[str, Engine]:
    """The tenant a token belongs to, and the database holding its records."""
    if not token:
        raise HTTPException(401, detail="PROVIDER_AUTHENTICATION_REQUIRED")
    tenant = TOKEN_MAP.get(token)
    if tenant is not None:
        if tenant not in TENANTS:
            raise HTTPException(403, detail="TENANT_SCOPE_DENIED")
        engine = store.engine
    else:
        with Session(store.engine) as db:
            row = db.scalar(
                select(store.SimulatorTenant).where(store.SimulatorTenant.api_key_hash == store.hash_key(token))
            )
        if row is None or row.status != "ACTIVE":
            raise HTTPException(401, detail="PROVIDER_AUTHENTICATION_REQUIRED")
        tenant, engine = row.tenant_key, store.tenant_engine(row.database_name)
    if requested and requested.upper() != tenant:
        raise HTTPException(403, detail="TENANT_SCOPE_DENIED")
    return tenant, engine


def require_admin(token: str | None) -> None:
    expected = os.getenv("SIMULATOR_ADMIN_TOKEN", "")
    if not expected:
        raise HTTPException(503, detail="SIMULATOR_ADMIN_TOKEN is not set on this simulator")
    if not token or not hmac.compare_digest(token, expected):
        raise HTTPException(401, detail="ADMIN_AUTHENTICATION_REQUIRED")


class RecordRequest(BaseModel):
    external_id: str = Field(min_length=1, max_length=255)
    record_version: str = Field(default="1", min_length=1, max_length=80)
    payload: dict


class TenantRequest(BaseModel):
    tenant_key: str = Field(pattern=r"^[A-Z][A-Z0-9_]{1,39}$", description="For example ACME_MEDICAL")


@app.get("/health")
def health():
    return {
        "status": "ok",
        "provider": PROVIDER,
        "database": "isolated",
        "port": APPLICATION.get("port") or PROVIDER_PORTS.get(PROVIDER),
    }


@app.get("/ready")
def ready():
    return {"status": "ready", "provider": PROVIDER, "database": "isolated"}


@app.get("/catalog")
def catalog():
    """The records this application holds, with their columns and key (no tenant data)."""
    return {"provider": PROVIDER, "name": APPLICATION["name"], "records": APPLICATION["records"]}


@app.post("/admin/tenants", status_code=201)
def create_tenant(payload: TenantRequest, x_admin_token: str | None = Header(None)):
    """Create a customer of this application: its own database and an API key, shown once."""
    require_admin(x_admin_token)
    if payload.tenant_key in TENANTS:
        raise HTTPException(409, detail="TENANT_EXISTS")
    database = store.tenant_database_name(payload.tenant_key)
    api_key = f"sk_{PROVIDER.lower()}_{secrets.token_urlsafe(24)}"
    with Session(store.engine) as db:
        if db.get(store.SimulatorTenant, payload.tenant_key) is not None:
            raise HTTPException(409, detail="TENANT_EXISTS")
        store.create_tenant_database(database)
        db.add(
            store.SimulatorTenant(
                tenant_key=payload.tenant_key,
                api_key_hash=store.hash_key(api_key),
                key_hint=api_key[-4:],
                database_name=database,
                status="ACTIVE",
                created_at=datetime.now(timezone.utc),
            )
        )
        db.commit()
    return {
        "provider": PROVIDER,
        "tenant_key": payload.tenant_key,
        "database": database,
        "api_key": api_key,
        "message": "Store this API key now: it is not shown again.",
    }


@app.get("/admin/tenants")
def list_tenants(x_admin_token: str | None = Header(None)):
    require_admin(x_admin_token)
    with Session(store.engine) as db:
        rows = db.scalars(select(store.SimulatorTenant).order_by(store.SimulatorTenant.tenant_key)).all()
        return {
            "provider": PROVIDER,
            "tenants": [
                {
                    "tenant_key": row.tenant_key,
                    "database": row.database_name,
                    "status": row.status,
                    "api_key_ends_with": row.key_hint,
                    "created_at": row.created_at,
                    "key_rotated_at": row.key_rotated_at,
                }
                for row in rows
            ],
        }


@app.post("/admin/tenants/{tenant_key}/rotate-key")
def rotate_key(tenant_key: str, x_admin_token: str | None = Header(None)):
    """Issue a new API key; the old one stops working at once."""
    require_admin(x_admin_token)
    api_key = f"sk_{PROVIDER.lower()}_{secrets.token_urlsafe(24)}"
    with Session(store.engine) as db:
        row = db.get(store.SimulatorTenant, tenant_key.upper())
        if row is None:
            raise HTTPException(404, detail="TENANT_NOT_FOUND")
        row.api_key_hash, row.key_hint = store.hash_key(api_key), api_key[-4:]
        row.key_rotated_at = datetime.now(timezone.utc)
        db.commit()
    return {"provider": PROVIDER, "tenant_key": tenant_key.upper(), "api_key": api_key}


@app.get("/whoami")
def whoami(x_provider_token: str | None = Header(None)):
    """Which tenant an API key belongs to, and how many records it holds per record type."""
    tenant_key, engine = tenant_from_token(x_provider_token, None)
    return {
        "provider": PROVIDER,
        "tenant_key": tenant_key,
        "records": store.record_counts(PROVIDER, tenant_key, engine),
    }


@app.get("/schema/{entity}")
def schema(entity: str, x_provider_token: str | None = Header(None), tenant: str | None = Query(None)):
    tenant_key, _ = tenant_from_token(x_provider_token, tenant)
    record = APPLICATION["records"].get(entity)
    fields = record["columns"] if record else schema_for(PROVIDER, entity)
    return {
        "provider": PROVIDER,
        "tenant_key": tenant_key,
        "entity": entity,
        "schema_version": "v2" if record else "v1",
        "fields": fields,
        "field_count": len(fields),
        "key": record["key"] if record else None,
    }


@app.get("/records/{entity}")
def records(entity: str, x_provider_token: str | None = Header(None), tenant: str | None = Query(None)):
    tenant_key, engine = tenant_from_token(x_provider_token, tenant)
    return {
        "provider": PROVIDER,
        "tenant_key": tenant_key,
        "entity": entity,
        "records": store.list_records(PROVIDER, tenant_key, entity, engine),
    }


@app.get("/records/{entity}/{external_id}/history")
def record_history(
    entity: str, external_id: str, x_provider_token: str | None = Header(None), tenant: str | None = Query(None)
):
    tenant_key, engine = tenant_from_token(x_provider_token, tenant)
    return {
        "provider": PROVIDER,
        "tenant_key": tenant_key,
        "entity": entity,
        "external_id": external_id,
        "history": store.history(PROVIDER, tenant_key, entity, external_id, engine),
    }


@app.post("/records/{entity}")
def write_record(
    entity: str, payload: RecordRequest, x_provider_token: str | None = Header(None), tenant: str | None = Query(None)
):
    tenant_key, engine = tenant_from_token(x_provider_token, tenant)
    return {
        "provider": PROVIDER,
        "tenant_key": tenant_key,
        "entity": entity,
        "record": store.upsert(
            PROVIDER, tenant_key, entity, payload.external_id, payload.record_version, payload.payload, engine
        ),
    }


def _rows_from_csv(entity: str, raw: bytes) -> tuple[list[tuple[str, dict]], list[dict]]:
    """Check a whole upload against the record's columns before anything is stored."""
    spec = APPLICATION["records"].get(entity)
    if spec is None:
        raise HTTPException(404, detail={"code": "UNKNOWN_RECORD_TYPE", "known": sorted(APPLICATION["records"])})
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(422, detail={"code": "NOT_UTF8", "message": "Save the file as UTF-8 CSV."}) from None
    reader = csv.DictReader(io.StringIO(text))
    header = [name.strip() for name in (reader.fieldnames or [])]
    problems: list[dict] = []
    unknown = [name for name in header if name not in spec["columns"]]
    missing = [name for name in spec["required"] + spec["key"] if name not in header]
    if unknown:
        problems.append({"row": 1, "message": f"Unknown columns: {', '.join(unknown)}"})
    if missing:
        problems.append({"row": 1, "message": f"Missing columns: {', '.join(dict.fromkeys(missing))}"})
    if problems:
        return [], problems
    rows: list[tuple[str, dict]] = []
    seen: dict[str, int] = {}
    for number, raw_row in enumerate(reader, start=2):
        if len(rows) >= MAX_UPLOAD_ROWS:
            problems.append({"row": number, "message": f"More than {MAX_UPLOAD_ROWS} rows; split the file."})
            break
        row = {(key or "").strip(): (value or "").strip() for key, value in raw_row.items() if key is not None}
        if None in raw_row:
            problems.append({"row": number, "message": "More values than columns; quote values that contain commas."})
            continue
        if not any(row.values()):
            continue
        empty = [name for name in spec["required"] if not row.get(name)]
        if empty:
            problems.append({"row": number, "message": f"Required value missing: {', '.join(empty)}"})
            continue
        key = "|".join(row[name] for name in spec["key"])
        if key in seen:
            problems.append({"row": number, "message": f"Same key as row {seen[key]}: {key}"})
            continue
        seen[key] = number
        rows.append((key, row))
    return rows, problems


@app.post("/records/{entity}/csv")
def upload_csv(
    entity: str,
    raw: bytes = Body(..., media_type="text/csv"),
    x_provider_token: str | None = Header(None),
):
    """Load a CSV file (the template for this record type): every row is stored, or none is if any row is wrong."""
    tenant_key, engine = tenant_from_token(x_provider_token, None)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, detail={"code": "FILE_TOO_LARGE", "max_bytes": MAX_UPLOAD_BYTES})
    rows, problems = _rows_from_csv(entity, raw)
    if problems:
        raise HTTPException(422, detail={"code": "CSV_REJECTED", "stored": 0, "problems": problems[:50]})
    if not rows:
        raise HTTPException(422, detail={"code": "CSV_EMPTY", "stored": 0, "problems": []})
    result = store.upsert_many(PROVIDER, tenant_key, entity, rows, engine)
    return {"provider": PROVIDER, "tenant_key": tenant_key, "entity": entity, "rows": len(rows), **result}


@app.delete("/records/{entity}")
def clear_entity(entity: str, x_provider_token: str | None = Header(None)):
    """Remove every record of one type for this tenant (to reload test data)."""
    tenant_key, engine = tenant_from_token(x_provider_token, None)
    return {
        "provider": PROVIDER,
        "tenant_key": tenant_key,
        "entity": entity,
        "removed": store.clear_records(PROVIDER, tenant_key, entity, engine),
    }


UPLOAD_PAGE = (Path(__file__).parent / "upload_page.html").read_text(encoding="utf-8")


@app.get("/", response_class=HTMLResponse)
def upload_page():
    return HTMLResponse(UPLOAD_PAGE.replace("{{APPLICATION}}", APPLICATION["name"]).replace("{{PROVIDER}}", PROVIDER))
