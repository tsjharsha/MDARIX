"""An organization's intake address (spec 4.3): ``cases-<token>@intake.mdarix.com``, stored in the control table
``inbound_provider_mappings`` (provider ``MDARIX_MAIL``, account = the local part). The token is random, so the address
never names or reveals the customer.

States: ``ACTIVE`` (the current address), ``OFF`` (switched off by the Customer Admin), ``ROTATED`` (replaced; still
accepted for 30 days after ``updated_at``), ``RETIRED`` (refused).
"""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from backend.app.db.models.stage3 import InboundProviderMapping
from backend.app.mail_in import PROVIDER, domain

ACTIVE, OFF, ROTATED, RETIRED = "ACTIVE", "OFF", "ROTATED", "RETIRED"
ROTATE_GRACE = timedelta(days=30)
_ALPHABET = "abcdefghijkmnpqrstuvwxyz23456789"  # no 0/o or 1/l: read aloud or copied from a screen


def new_local_part() -> str:
    return "cases-" + "".join(secrets.choice(_ALPHABET) for _ in range(12))  # about 60 random bits


def tenant_for(control: Session, local_part: str, now: datetime) -> uuid.UUID | None:
    """The organization an address belongs to, if mail to it is accepted now."""
    row = (
        control.query(InboundProviderMapping)
        .filter(
            InboundProviderMapping.provider == PROVIDER,
            InboundProviderMapping.provider_account_id == local_part.strip().lower(),
        )
        .first()
    )
    if row is None:
        return None
    if row.status == ACTIVE or (row.status == ROTATED and now - row.updated_at < ROTATE_GRACE):
        return row.tenant_id
    return None


def _rows(control: Session, tenant_id) -> list[InboundProviderMapping]:
    return (
        control.query(InboundProviderMapping)
        .filter(InboundProviderMapping.provider == PROVIDER, InboundProviderMapping.tenant_id == tenant_id)
        .order_by(InboundProviderMapping.created_at.desc())
        .all()
    )


def view(control: Session, tenant_id, now: datetime) -> dict:
    rows = _rows(control, tenant_id)
    current = next((row for row in rows if row.status in (ACTIVE, OFF)), None)
    old = [row for row in rows if row.status == ROTATED and now - row.updated_at < ROTATE_GRACE]
    return {
        "address": f"{current.provider_account_id}@{domain()}" if current else None,
        "on": bool(current and current.status == ACTIVE),
        "old_addresses": [
            {"address": f"{row.provider_account_id}@{domain()}", "until": (row.updated_at + ROTATE_GRACE).isoformat()}
            for row in old
        ],
    }


def _add(control: Session, tenant_id, now: datetime) -> InboundProviderMapping:
    row = InboundProviderMapping(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        provider=PROVIDER,
        provider_account_id=new_local_part(),
        status=ACTIVE,
        created_at=now,
        updated_at=now,
    )
    control.add(row)
    return row


def switch(control: Session, tenant_id, on: bool, now: datetime) -> None:
    """On: the current address (made on first use) accepts mail. Off: nothing is accepted, old addresses included."""
    rows = _rows(control, tenant_id)
    current = next((row for row in rows if row.status in (ACTIVE, OFF)), None)
    if on and current is None:
        _add(control, tenant_id, now)
        return
    if current is not None:
        current.status, current.updated_at = (ACTIVE if on else OFF), now
    if not on:
        for row in rows:
            if row.status == ROTATED:
                row.status, row.updated_at = RETIRED, now


def rotate(control: Session, tenant_id, now: datetime) -> None:
    """A new address; the old one keeps working for 30 days (ROTATED), then is refused."""
    for row in _rows(control, tenant_id):
        if row.status == ACTIVE:
            row.status, row.updated_at = ROTATED, now
        elif row.status == OFF:
            row.status, row.updated_at = RETIRED, now
    _add(control, tenant_id, now)
