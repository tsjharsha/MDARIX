"""Regulatory reference data (G2a).

- Each product's regulatory identity (UDI-DI, GMDN) and its registrations per market.
- The organization's responsible party in each market, by legal role, with contacts.
- IMDRF codes, Annexes A-G by release, read from the shared ``imdrf_codes`` (loaded from IMDRF's own files by
  scripts/load_imdrf_annex.py; nothing here invents a code).
- The organization's own codes mapped to IMDRF codes, many-to-many: one person proposes, a different person with
  regulatory approval rights approves or rejects. Report worksheets read only approved mappings
  (``approved_imdrf_codes``).
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.db.models.foundation import Product
from backend.app.db.models.regulatory_reference import (
    ANNEXES,
    MARKETS,
    PARTY_ROLES,
    ImdrfCode,
    ImdrfCodeMapping,
    MarketResponsibleParty,
    ProductRegistration,
)

# The kinds of registration each market knows. GB: Great Britain; NI: Northern Ireland, which follows EU MDR.
REGISTRATION_TYPES = {
    "US": ("510K", "PMA", "DE_NOVO", "EXEMPT"),
    "EU": ("CE",),
    "GB": ("UKCA", "CE"),
    "NI": ("CE", "UKNI"),
    "CA": ("MDL",),
    "IN": ("CDSCO_LICENCE",),
    "AU": ("ARTG",),
}
_GMDN_CODE = re.compile(r"^\d{5}$")


def _bad(code: str, message: str, status: int = 422):
    return HTTPException(status, detail={"code": code, "message": message})


def _text(value, limit: int) -> str | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        value = str(value)  # a number sent as a JSON number, e.g. a registration number
    value = value.strip() if isinstance(value, str) else None
    if value and len(value) > limit:
        raise _bad("VALUE_TOO_LONG", f"Keep it to {limit} characters")
    return value or None


def check_registration(payload: dict) -> dict:
    """A registration as stored, or 422 naming what is wrong. US registrations need the FDA product code; EU and NI
    CE marks name the notified body."""
    market = str(payload.get("market", "")).upper()
    if market not in MARKETS:
        raise _bad("MARKET_UNKNOWN", f"Market must be one of {', '.join(MARKETS)}")
    kind = str(payload.get("registration_type", "")).upper()
    if kind not in REGISTRATION_TYPES[market]:
        raise _bad("REGISTRATION_TYPE_UNKNOWN", f"{market} registrations are {', '.join(REGISTRATION_TYPES[market])}")
    number = _text(payload.get("registration_number"), 120)
    if not number:
        raise _bad("REGISTRATION_NUMBER_REQUIRED", "Give the registration or licence number")
    product_code = _text(payload.get("product_code"), 20)
    if market == "US" and not product_code:
        raise _bad("PRODUCT_CODE_REQUIRED", "A US registration needs its FDA product code")
    body_name, body_number = _text(payload.get("body_name"), 200), _text(payload.get("body_number"), 20)
    if market in ("EU", "NI") and kind == "CE" and not (body_name and body_number):
        raise _bad("NOTIFIED_BODY_REQUIRED", "A CE mark names its notified body and number")
    return {
        "market": market,
        "registration_type": kind,
        "registration_number": number,
        "product_code": product_code,
        "body_name": body_name,
        "body_number": body_number,
    }


def check_identity(payload: dict) -> dict:
    gmdn_code = _text(payload.get("gmdn_code"), 10)
    if gmdn_code and not _GMDN_CODE.match(gmdn_code):
        raise _bad("GMDN_CODE_INVALID", "A GMDN code is five digits")
    return {
        "udi_di": _text(payload.get("udi_di"), 80),
        "gmdn_code": gmdn_code,
        "gmdn_term": _text(payload.get("gmdn_term"), 300),
    }


def check_party(payload: dict) -> dict:
    market, role = str(payload.get("market", "")).upper(), str(payload.get("role", "")).upper()
    if market not in MARKETS:
        raise _bad("MARKET_UNKNOWN", f"Market must be one of {', '.join(MARKETS)}")
    if role not in PARTY_ROLES:
        raise _bad("ROLE_UNKNOWN", f"Role must be one of {', '.join(PARTY_ROLES)}")
    organisation = _text(payload.get("organisation"), 200)
    if not organisation:
        raise _bad("ORGANISATION_REQUIRED", "Name the responsible organization")
    email = _text(payload.get("contact_email"), 254)
    if email and "@" not in email:
        raise _bad("EMAIL_INVALID", "Give a valid e-mail address")
    return {
        "market": market,
        "role": role,
        "organisation": organisation,
        "address": _text(payload.get("address"), 2000),
        "contact_name": _text(payload.get("contact_name"), 200),
        "contact_email": email,
        "contact_phone": _text(payload.get("contact_phone"), 40),
    }


def _insert(db: Session, item, code: str, message: str) -> None:
    """Add a row, answering 409 if the same row arrived at the same moment (the unique rule caught it); the
    savepoint keeps the rest of the request's work."""
    try:
        with db.begin_nested():
            db.add(item)
            db.flush()
    except IntegrityError as exc:
        raise _bad(code, message, 409) from exc


def _product(db: Session, tenant_id, product_id: uuid.UUID) -> Product:
    product = db.query(Product).filter(Product.tenant_id == tenant_id, Product.id == product_id).one_or_none()
    if product is None:
        raise _bad("PRODUCT_NOT_FOUND", "No such product", 404)
    return product


def _registration_view(item: ProductRegistration) -> dict:
    return {
        "id": str(item.id),
        "market": item.market,
        "registration_type": item.registration_type,
        "registration_number": item.registration_number,
        "product_code": item.product_code,
        "body_name": item.body_name,
        "body_number": item.body_number,
    }


def _party_view(item: MarketResponsibleParty) -> dict:
    return {
        "id": str(item.id),
        "market": item.market,
        "role": item.role,
        "organisation": item.organisation,
        "address": item.address,
        "contact_name": item.contact_name,
        "contact_email": item.contact_email,
        "contact_phone": item.contact_phone,
    }


def product_profile(db: Session, tenant_id, product_id: uuid.UUID) -> dict:
    """A product's regulatory identity, its registrations, and the responsible party in each market it is
    registered in."""
    product = _product(db, tenant_id, product_id)
    registrations = (
        db.query(ProductRegistration)
        .filter(ProductRegistration.tenant_id == tenant_id, ProductRegistration.product_id == product_id)
        .order_by(ProductRegistration.market, ProductRegistration.registration_number)
        .all()
    )
    markets = sorted({item.market for item in registrations})
    parties = (
        db.query(MarketResponsibleParty)
        .filter(MarketResponsibleParty.tenant_id == tenant_id, MarketResponsibleParty.market.in_(markets))
        .order_by(MarketResponsibleParty.market, MarketResponsibleParty.role)
        .all()
        if markets
        else []
    )
    return {
        "product_id": str(product.id),
        "product_identifier": product.product_identifier,
        "name": product.name,
        "udi_di": product.udi_di,
        "gmdn_code": product.gmdn_code,
        "gmdn_term": product.gmdn_term,
        "registrations": [_registration_view(item) for item in registrations],
        "responsible_parties": [_party_view(item) for item in parties],
        "markets_without_party": [m for m in markets if m not in {p.market for p in parties}],
    }


def set_identity(db: Session, tenant_id, product_id: uuid.UUID, payload: dict) -> dict:
    product = _product(db, tenant_id, product_id)
    for column, value in check_identity(payload).items():
        setattr(product, column, value)
    product.updated_at = datetime.now(timezone.utc)
    return product_profile(db, tenant_id, product_id)


def add_registration(db: Session, tenant_id, product_id: uuid.UUID, payload: dict) -> dict:
    _product(db, tenant_id, product_id)
    values = check_registration(payload)
    exists = (
        db.query(ProductRegistration.id)
        .filter(
            ProductRegistration.tenant_id == tenant_id,
            ProductRegistration.product_id == product_id,
            ProductRegistration.market == values["market"],
            ProductRegistration.registration_number == values["registration_number"],
        )
        .first()
    )
    if exists:
        raise _bad("REGISTRATION_EXISTS", "This product already has that registration in that market", 409)
    now = datetime.now(timezone.utc)
    item = ProductRegistration(tenant_id=tenant_id, product_id=product_id, created_at=now, updated_at=now, **values)
    _insert(db, item, "REGISTRATION_EXISTS", "This product already has that registration in that market")
    return _registration_view(item)


def remove_registration(db: Session, tenant_id, product_id: uuid.UUID, registration_id: uuid.UUID) -> None:
    deleted = (
        db.query(ProductRegistration)
        .filter(
            ProductRegistration.tenant_id == tenant_id,
            ProductRegistration.product_id == product_id,
            ProductRegistration.id == registration_id,
        )
        .delete(synchronize_session=False)
    )
    if not deleted:
        raise _bad("REGISTRATION_NOT_FOUND", "No such registration", 404)


def responsible_parties(db: Session, tenant_id) -> list[dict]:
    items = (
        db.query(MarketResponsibleParty)
        .filter(MarketResponsibleParty.tenant_id == tenant_id)
        .order_by(MarketResponsibleParty.market, MarketResponsibleParty.role)
        .all()
    )
    return [_party_view(item) for item in items]


def set_party(db: Session, tenant_id, payload: dict) -> dict:
    """Set the responsible party for one market and role (one per pair; setting it again replaces it)."""
    values = check_party(payload)
    now = datetime.now(timezone.utc)
    item = (
        db.query(MarketResponsibleParty)
        .filter(
            MarketResponsibleParty.tenant_id == tenant_id,
            MarketResponsibleParty.market == values["market"],
            MarketResponsibleParty.role == values["role"],
        )
        .one_or_none()
    )
    if item is None:
        item = MarketResponsibleParty(tenant_id=tenant_id, created_at=now, updated_at=now, **values)
        _insert(db, item, "PARTY_EXISTS", "A responsible party for this market and role was just set; reload")
    else:
        for column, value in values.items():
            setattr(item, column, value)
        item.updated_at = now
    db.flush()
    return _party_view(item)


def remove_party(db: Session, tenant_id, party_id: uuid.UUID) -> None:
    deleted = (
        db.query(MarketResponsibleParty)
        .filter(MarketResponsibleParty.tenant_id == tenant_id, MarketResponsibleParty.id == party_id)
        .delete(synchronize_session=False)
    )
    if not deleted:
        raise _bad("PARTY_NOT_FOUND", "No such responsible party", 404)


# --- IMDRF codes (shared reference data, read from the control database) -----------------------------------------


def releases(control: Session) -> list[dict]:
    from sqlalchemy import func

    rows = (
        control.query(ImdrfCode.release, ImdrfCode.annex, func.count())
        .group_by(ImdrfCode.release, ImdrfCode.annex)
        .order_by(ImdrfCode.release.desc(), ImdrfCode.annex)
        .all()
    )
    out: dict[str, dict] = {}
    for release, annex, count in rows:
        out.setdefault(release, {"release": release, "annexes": {}})["annexes"][annex] = count
    return list(out.values())


def search_codes(control: Session, release: str, annex: str | None, text: str | None, limit: int = 50) -> list[dict]:
    query = control.query(ImdrfCode).filter(ImdrfCode.release == release)
    if annex:
        query = query.filter(ImdrfCode.annex == annex.upper())
    if text:
        pattern = f"%{text.strip()[:100]}%"
        query = query.filter((ImdrfCode.code.ilike(pattern)) | (ImdrfCode.term.ilike(pattern)))
    return [
        {
            "release": item.release,
            "annex": item.annex,
            "code": item.code,
            "term": item.term,
            "definition": item.definition,
            "parent_code": item.parent_code,
        }
        for item in query.order_by(ImdrfCode.annex, ImdrfCode.code).limit(min(limit, 200)).all()
    ]


# --- The organization's codes mapped to IMDRF -----------------------------------------------------------------


def _mapping_view(item: ImdrfCodeMapping) -> dict:
    return {
        "id": str(item.id),
        "customer_system": item.customer_system,
        "customer_code": item.customer_code,
        "customer_term": item.customer_term,
        "release": item.release,
        "annex": item.annex,
        "imdrf_code": item.imdrf_code,
        "status": item.status,
        "proposed_by": item.proposed_by,
        "proposed_at": item.proposed_at.isoformat(),
        "reviewed_by": item.reviewed_by,
        "reviewed_at": item.reviewed_at.isoformat() if item.reviewed_at else None,
        "review_note": item.review_note,
    }


def propose_mapping(db: Session, control: Session, tenant_id, payload: dict, actor: str) -> dict:
    """Propose one link from the organization's code to an IMDRF code of a loaded release. A code may link to several
    IMDRF codes and several codes to one (many-to-many); the same link twice is refused."""
    system = _text(payload.get("customer_system"), 80)
    code = _text(payload.get("customer_code"), 120)
    release = _text(payload.get("release"), 20)
    annex = str(payload.get("annex", "")).upper()
    imdrf_code = _text(payload.get("imdrf_code"), 20)
    if not (system and code and release and imdrf_code) or annex not in ANNEXES:
        raise _bad(
            "MAPPING_INCOMPLETE", "Give the code system, the code, the release, the annex (A-G) and the IMDRF code"
        )
    known = (
        control.query(ImdrfCode.id)
        .filter(ImdrfCode.release == release, ImdrfCode.annex == annex, ImdrfCode.code == imdrf_code)
        .first()
    )
    if not known:
        raise _bad("IMDRF_CODE_UNKNOWN", f"{imdrf_code} is not in Annex {annex} of release {release}")
    duplicate = (
        db.query(ImdrfCodeMapping.id)
        .filter(
            ImdrfCodeMapping.tenant_id == tenant_id,
            ImdrfCodeMapping.customer_system == system,
            ImdrfCodeMapping.customer_code == code,
            ImdrfCodeMapping.release == release,
            ImdrfCodeMapping.annex == annex,
            ImdrfCodeMapping.imdrf_code == imdrf_code,
        )
        .first()
    )
    if duplicate:
        raise _bad("MAPPING_EXISTS", "This link is already proposed or decided", 409)
    item = ImdrfCodeMapping(
        tenant_id=tenant_id,
        customer_system=system,
        customer_code=code,
        customer_term=_text(payload.get("customer_term"), 300),
        release=release,
        annex=annex,
        imdrf_code=imdrf_code,
        status="PROPOSED",
        proposed_by=actor,
        proposed_at=datetime.now(timezone.utc),
    )
    _insert(db, item, "MAPPING_EXISTS", "This link is already proposed or decided")
    return _mapping_view(item)


def review_mapping(db: Session, tenant_id, mapping_id: uuid.UUID, approve: bool, note: str | None, actor: str) -> dict:
    """Approve or reject a proposed link. The person who proposed it may not decide it; a rejection gives a reason."""
    item = (
        db.query(ImdrfCodeMapping)
        .filter(ImdrfCodeMapping.tenant_id == tenant_id, ImdrfCodeMapping.id == mapping_id)
        .with_for_update()
        .one_or_none()
    )
    if item is None:
        raise _bad("MAPPING_NOT_FOUND", "No such mapping", 404)
    if item.status != "PROPOSED":
        raise _bad("MAPPING_DECIDED", "This mapping was already decided", 409)
    if item.proposed_by == actor:
        raise _bad("MAPPING_SELF_REVIEW", "Another person must review a mapping you proposed", 403)
    note = _text(note, 2000)
    if not approve and not note:
        raise _bad("REASON_REQUIRED", "Say why the mapping is rejected")
    item.status = "APPROVED" if approve else "REJECTED"
    item.reviewed_by = actor
    item.reviewed_at = datetime.now(timezone.utc)
    item.review_note = note
    return _mapping_view(item)


def mappings(db: Session, tenant_id, status: str | None = None, customer_system: str | None = None) -> list[dict]:
    query = db.query(ImdrfCodeMapping).filter(ImdrfCodeMapping.tenant_id == tenant_id)
    if status:
        query = query.filter(ImdrfCodeMapping.status == status)
    if customer_system:
        query = query.filter(ImdrfCodeMapping.customer_system == customer_system)
    items = query.order_by(ImdrfCodeMapping.customer_system, ImdrfCodeMapping.customer_code, ImdrfCodeMapping.annex)
    return [_mapping_view(item) for item in items.limit(2000).all()]


def approved_imdrf_codes(db: Session, tenant_id, customer_system: str, customer_code: str, release: str) -> list[tuple]:
    """The IMDRF (annex, code) pairs an organization's code maps to, approved links only: what report worksheets use."""
    rows = (
        db.query(ImdrfCodeMapping.annex, ImdrfCodeMapping.imdrf_code)
        .filter(
            ImdrfCodeMapping.tenant_id == tenant_id,
            ImdrfCodeMapping.customer_system == customer_system,
            ImdrfCodeMapping.customer_code == customer_code,
            ImdrfCodeMapping.release == release,
            ImdrfCodeMapping.status == "APPROVED",
        )
        .order_by(ImdrfCodeMapping.annex, ImdrfCodeMapping.imdrf_code)
        .all()
    )
    return [tuple(row) for row in rows]


def approved_links(db: Session, control: Session, tenant_id, customer_system: str, codes: list[str]) -> dict:
    """``{customer code: [{release, annex, code, term}]}``: the approved IMDRF links of these codes, with each IMDRF
    term as loaded (the mapping's own release first, else the newest release that has the code; None when no release
    holds it yet). What a complaint shows beside its problem code."""
    codes = [code for code in dict.fromkeys(codes) if code][:200]
    if not codes:
        return {}
    rows = (
        db.query(ImdrfCodeMapping)
        .filter(
            ImdrfCodeMapping.tenant_id == tenant_id,
            ImdrfCodeMapping.customer_system == customer_system,
            ImdrfCodeMapping.customer_code.in_(codes),
            ImdrfCodeMapping.status == "APPROVED",
        )
        .order_by(ImdrfCodeMapping.customer_code, ImdrfCodeMapping.annex, ImdrfCodeMapping.imdrf_code)
        .all()
    )
    wanted = {(item.annex, item.imdrf_code) for item in rows}
    terms: dict[tuple, dict[str, str]] = {}
    if wanted:
        for item in control.query(ImdrfCode).filter(ImdrfCode.code.in_({code for _, code in wanted})).all():
            terms.setdefault((item.annex, item.code), {})[item.release] = item.term
    out: dict[str, list[dict]] = {}
    for item in rows:
        by_release = terms.get((item.annex, item.imdrf_code), {})
        term = by_release.get(item.release) or (by_release[max(by_release)] if by_release else None)
        out.setdefault(item.customer_code, []).append(
            {"release": item.release, "annex": item.annex, "code": item.imdrf_code, "term": term}
        )
    return out
