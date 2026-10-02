"""Small persistent store used by the external-provider simulator.

The simulator deliberately has its own database URL. It never imports MDARIX
models and therefore cannot read or write the MDARIX business database.

Each customer (tenant) registered through the admin API gets its own database on the simulator's server, the way
each customer runs its own TrackWise or SAP. The four original test tenants (TENANT_A..D, configured by
SIMULATOR_TENANT_TOKENS) keep their records in the shared base database.
"""

from datetime import datetime, timezone
from functools import lru_cache
import hashlib
import json
import os
import re
from sqlalchemy import DateTime, Integer, String, Text, create_engine, delete, func, select, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column


class Base(DeclarativeBase):
    pass


class RegistryBase(DeclarativeBase):
    pass


class SourceRecord(Base):
    __tablename__ = "provider_source_records"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_key: Mapped[str] = mapped_column(String(80), index=True)
    provider: Mapped[str] = mapped_column(String(80), index=True)
    source_entity: Mapped[str] = mapped_column(String(120), index=True)
    external_id: Mapped[str] = mapped_column(String(255), index=True)
    record_version: Mapped[str] = mapped_column(String(80))
    payload: Mapped[str] = mapped_column(Text())
    fingerprint: Mapped[str] = mapped_column(String(64))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SourceRecordHistory(Base):
    __tablename__ = "provider_source_record_history"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_key: Mapped[str] = mapped_column(String(80), index=True)
    provider: Mapped[str] = mapped_column(String(80))
    source_entity: Mapped[str] = mapped_column(String(120))
    external_id: Mapped[str] = mapped_column(String(255))
    record_version: Mapped[str] = mapped_column(String(80))
    payload: Mapped[str] = mapped_column(Text())
    fingerprint: Mapped[str] = mapped_column(String(64))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SimulatorTenant(RegistryBase):
    """A customer of this simulated application: its own database and the hash of its API key."""

    __tablename__ = "simulator_tenants"
    tenant_key: Mapped[str] = mapped_column(String(40), primary_key=True)
    api_key_hash: Mapped[str] = mapped_column(String(64), unique=True)
    key_hint: Mapped[str] = mapped_column(String(8))
    database_name: Mapped[str] = mapped_column(String(63))
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    key_rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


TENANT_KEY = re.compile(r"^[A-Z][A-Z0-9_]{1,39}$")


def base_url() -> str:
    return os.getenv("SIMULATOR_DATABASE_URL", "sqlite:///source-simulator.db")


def _make_engine(url: str) -> Engine:
    return create_engine(url, pool_pre_ping=True)


def _ensure_base_database() -> None:
    """Simulators that share one Postgres server each create their own base database on first start."""
    url = make_url(base_url())
    if url.get_backend_name() == "sqlite" or not url.database:
        return
    if not re.fullmatch(r"[a-z][a-z0-9_]{1,62}", url.database):
        raise ValueError("INVALID_DATABASE_NAME")
    server = _make_engine(url.set(database="postgres").render_as_string(hide_password=False))
    try:
        with server.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            if not connection.scalar(text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": url.database}):
                connection.execute(text(f'CREATE DATABASE "{url.database}"'))
    finally:
        server.dispose()


_ensure_base_database()
engine = _make_engine(base_url())
Base.metadata.create_all(engine)
RegistryBase.metadata.create_all(engine)


def hash_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode()).hexdigest()


def tenant_database_name(tenant_key: str) -> str:
    """The tenant's own database: <base database>_<tenant key>, for example trackwise_acme_medical."""
    base = make_url(base_url())
    if base.get_backend_name() == "sqlite":
        stem = (base.database or "source-simulator.db").removesuffix(".db")
        return f"{stem}-{tenant_key.lower()}.db"
    return f"{base.database}_{tenant_key.lower()}"[:63]


def _tenant_url(database_name: str) -> str:
    base = make_url(base_url())
    if base.get_backend_name() == "sqlite":
        return f"sqlite:///{database_name}"
    return base.set(database=database_name).render_as_string(hide_password=False)


def create_tenant_database(database_name: str) -> None:
    """Create the tenant's database on the simulator's server (a file for SQLite) and its tables."""
    if make_url(base_url()).get_backend_name() != "sqlite":
        if not re.fullmatch(r"[a-z][a-z0-9_]{1,62}", database_name):
            raise ValueError("INVALID_DATABASE_NAME")
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            exists = connection.scalar(text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": database_name})
            if not exists:
                connection.execute(text(f'CREATE DATABASE "{database_name}"'))
    Base.metadata.create_all(tenant_engine(database_name))


@lru_cache(maxsize=64)
def tenant_engine(database_name: str) -> Engine:
    return _make_engine(_tenant_url(database_name))


def _json(value: dict) -> dict:
    return json.loads(value) if isinstance(value, str) else value


def _upsert(db: Session, provider: str, tenant_key: str, entity: str, external_id: str, version: str, payload: dict):
    now = datetime.now(timezone.utc)
    clean = dict(payload)
    clean["tenant_key"] = tenant_key
    fingerprint = hashlib.sha256(json.dumps(clean, sort_keys=True).encode()).hexdigest()
    current = db.scalar(
        select(SourceRecord).where(
            SourceRecord.tenant_key == tenant_key,
            SourceRecord.provider == provider,
            SourceRecord.source_entity == entity,
            SourceRecord.external_id == external_id,
        )
    )
    outcome = "CREATED"
    if current is None:
        current = SourceRecord(
            tenant_key=tenant_key,
            provider=provider,
            source_entity=entity,
            external_id=external_id,
            record_version=version,
            payload=json.dumps(clean),
            fingerprint=fingerprint,
            updated_at=now,
        )
        db.add(current)
    elif current.fingerprint != fingerprint:
        outcome = "UPDATED"
        db.add(
            SourceRecordHistory(
                tenant_key=tenant_key,
                provider=provider,
                source_entity=entity,
                external_id=external_id,
                record_version=current.record_version,
                payload=json.dumps(_json(current.payload)),
                fingerprint=current.fingerprint,
                recorded_at=now,
            )
        )
        current.record_version = version
        current.payload = json.dumps(clean)
        current.fingerprint = fingerprint
        current.updated_at = now
    else:
        outcome = "DUPLICATE"
    return current, outcome


def upsert(
    provider: str,
    tenant_key: str,
    entity: str,
    external_id: str,
    version: str,
    payload: dict,
    store: Engine | None = None,
) -> dict:
    with Session(store or engine) as db:
        current, outcome = _upsert(db, provider, tenant_key, entity, external_id, version, payload)
        db.commit()
        return {
            "external_id": external_id,
            "record_version": current.record_version,
            "fingerprint": current.fingerprint,
            "payload": _json(current.payload),
            "outcome": outcome,
        }


def upsert_many(provider: str, tenant_key: str, entity: str, rows: list[tuple[str, dict]], store: Engine) -> dict:
    """Write a whole upload in one transaction: every row is stored, or none is."""
    counts = {"CREATED": 0, "UPDATED": 0, "DUPLICATE": 0}
    with Session(store) as db:
        for external_id, payload in rows:
            current = db.scalar(
                select(SourceRecord.record_version).where(
                    SourceRecord.tenant_key == tenant_key,
                    SourceRecord.provider == provider,
                    SourceRecord.source_entity == entity,
                    SourceRecord.external_id == external_id,
                )
            )
            version = str(int(current) + 1) if current and current.isdigit() else "1"
            _, outcome = _upsert(db, provider, tenant_key, entity, external_id, version, payload)
            db.flush()
            counts[outcome] += 1
        db.commit()
    return {"created": counts["CREATED"], "updated": counts["UPDATED"], "unchanged": counts["DUPLICATE"]}


def clear_records(provider: str, tenant_key: str, entity: str, store: Engine) -> int:
    with Session(store) as db:
        where = (
            SourceRecord.provider == provider,
            SourceRecord.tenant_key == tenant_key,
            SourceRecord.source_entity == entity,
        )
        removed = db.scalar(select(func.count()).select_from(SourceRecord).where(*where)) or 0
        db.execute(delete(SourceRecord).where(*where))
        db.execute(
            delete(SourceRecordHistory).where(
                SourceRecordHistory.provider == provider,
                SourceRecordHistory.tenant_key == tenant_key,
                SourceRecordHistory.source_entity == entity,
            )
        )
        db.commit()
        return removed


def record_counts(provider: str, tenant_key: str, store: Engine) -> dict[str, int]:
    with Session(store) as db:
        rows = db.execute(
            select(SourceRecord.source_entity, func.count())
            .where(SourceRecord.provider == provider, SourceRecord.tenant_key == tenant_key)
            .group_by(SourceRecord.source_entity)
        ).all()
        return {entity: count for entity, count in rows}


def list_records(provider: str, tenant_key: str, entity: str, store: Engine | None = None) -> list[dict]:
    with Session(store or engine) as db:
        rows = db.scalars(
            select(SourceRecord)
            .where(
                SourceRecord.provider == provider,
                SourceRecord.tenant_key == tenant_key,
                SourceRecord.source_entity == entity,
            )
            .order_by(SourceRecord.external_id)
        ).all()
        return [
            {**_json(row.payload), "external_id": row.external_id, "record_version": row.record_version} for row in rows
        ]


def history(provider: str, tenant_key: str, entity: str, external_id: str, store: Engine | None = None) -> list[dict]:
    with Session(store or engine) as db:
        rows = db.scalars(
            select(SourceRecordHistory)
            .where(
                SourceRecordHistory.provider == provider,
                SourceRecordHistory.tenant_key == tenant_key,
                SourceRecordHistory.source_entity == entity,
                SourceRecordHistory.external_id == external_id,
            )
            .order_by(SourceRecordHistory.recorded_at)
        ).all()
        return [
            {
                "external_id": row.external_id,
                "record_version": row.record_version,
                "payload": _json(row.payload),
                "recorded_at": row.recorded_at,
            }
            for row in rows
        ]
