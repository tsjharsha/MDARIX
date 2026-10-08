"""The generic administrator edit route cannot approve, release or alter an approved mapping.

A mapping reaches READY_FOR_APPROVAL, APPROVED and RELEASED only through the release workflow, where a second
administrator approves, and what was approved stays as approved: the edit route refuses to set a status at all and
refuses every change to a mapping under review, approved or released. A request for approval that nobody has
approved yet may still be withdrawn; an approved or released mapping leaves its state only by rolling back.
"""

import uuid

from backend.app.db.models.foundation import MappingConfiguration
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from tests.test_mapping_release_self_approval import RULES, _action, _admin, _audit_actions, _mapping, _organization

EDIT = "/api/v1/admin/control-plane/mappings/{}"
STATUS = "/api/v1/admin/configuration/mappings/{}/status"
# The same targets read from a renamed source column: an edit the release gate accepts.
EDITED_RULES = {("complaint_ref" if source == "complaint_number" else source): rule for source, rule in RULES.items()}


def _stored(mapping_id: str) -> tuple[str, dict]:
    db = SessionLocal()
    try:
        bind_system(db, "test: read the mapping")
        row = db.query(MappingConfiguration).filter(MappingConfiguration.id == uuid.UUID(mapping_id)).one()
        return row.status, dict(row.mapping_rules or {})
    finally:
        db.close()


def test_the_edit_route_never_sets_a_status_and_never_touches_a_governed_mapping():
    tenant = _organization()
    admin, _ = _admin(tenant)
    mapping = _mapping(admin)

    for status in ("RELEASED", "APPROVED", "DRAFT"):
        refused = admin.patch(EDIT.format(mapping), json={"values": {"status": status}})
        assert refused.status_code == 409, refused.text
        assert refused.json()["detail"]["code"] == "MAPPING_STATUS_GOVERNED"
    # A draft's rules are the administrator's to edit here.
    edited = admin.patch(EDIT.format(mapping), json={"values": {"mapping_rules": EDITED_RULES}})
    assert edited.status_code == 200, edited.text
    assert _stored(mapping) == ("DRAFT", EDITED_RULES)

    assert _action(admin, mapping, "REQUEST_APPROVAL").status_code == 200
    frozen = admin.patch(EDIT.format(mapping), json={"values": {"mapping_rules": RULES}})
    assert frozen.status_code == 409 and frozen.json()["detail"]["code"] == "MAPPING_FROZEN", frozen.text
    # Not approved yet: the request can be withdrawn, then made again.
    withdrawn = admin.patch(STATUS.format(mapping), json={"status": "DRAFT"})
    assert withdrawn.status_code == 200, withdrawn.text
    assert _action(admin, mapping, "REQUEST_APPROVAL").status_code == 200
    assert _action(admin, mapping, "APPROVE").status_code == 200  # the organization's only administrator, with a reason
    assert _action(admin, mapping, "PROMOTE").status_code == 200
    assert _stored(mapping) == ("RELEASED", EDITED_RULES)

    for values in ({"mapping_rules": RULES}, {"target_entity": "Product"}, {"version": "v2"}, {"code": "OTHER"}):
        frozen = admin.patch(EDIT.format(mapping), json={"values": values})
        assert frozen.status_code == 409 and frozen.json()["detail"]["code"] == "MAPPING_FROZEN", frozen.text
    back = admin.patch(STATUS.format(mapping), json={"status": "DRAFT"})
    assert back.status_code == 409 and back.json()["detail"]["code"] == "MAPPING_STATUS_GOVERNED", back.text
    assert _stored(mapping) == ("RELEASED", EDITED_RULES)

    assert _action(admin, mapping, "ROLLBACK").status_code == 200
    assert _stored(mapping)[0] == "SUPERSEDED"
    # Only the draft edit was recorded; every refusal changed nothing.
    assert _audit_actions(mapping).count("MAPPING_UPDATED") == 1
