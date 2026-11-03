"""A complaint's linked service work (release 0.10.71, Release A, A5; migration tr12sampleservice).

Narrow on purpose: the reference of the service work as the customer's own service system names it (free text, such
as a service ticket ID), who owns it, and its status (open, in progress, complete) with the date it was recorded. No
scheduling, parts or technicians: MDARIX is not a service-ticket system.

Service and quality are separate decisions. Completing the service **never** closes or advances the complaint, its
market assessments, its checklist or its readiness: the complaint's header then says "Service complete · Quality
assessment open", with the quality owner and the complaint's own next action.
"""

from __future__ import annotations

STATUSES = {"OPEN": "Open", "IN_PROGRESS": "In progress", "COMPLETE": "Complete"}
REFERENCE_MAX = 120
COMPLETE_LINE = "Service complete · Quality assessment open"


def problem(reference: str, status: str, owner: str | None, people: set[str]) -> str | None:
    """Why the service work cannot be recorded, or None."""
    if len(reference) < 2:
        return "Give the service work's reference, as your service system names it"
    if len(reference) > REFERENCE_MAX:
        return f"Keep the reference to {REFERENCE_MAX} characters"
    if status not in STATUSES:
        return "Choose its status: open, in progress or complete"
    if owner and owner not in people:
        return "Choose the owner among your organization's people"
    return None


def view(complaint, names: dict[str, str]) -> dict | None:
    """The complaint's service work as the complaint page shows it; None when none is linked."""
    if not complaint.service_reference:
        return None
    owner = complaint.service_owner
    return {
        "reference": complaint.service_reference,
        "owner_id": owner,
        "owner_name": names.get(owner) if owner else None,
        "status": complaint.service_status,
        "status_label": STATUSES.get(complaint.service_status or "", "Not known"),
        "status_at": complaint.service_status_at.isoformat() if complaint.service_status_at else None,
        # The header's line once the service is complete: the quality work stays open, whatever the service did.
        "header": COMPLETE_LINE if complaint.service_status == "COMPLETE" else None,
    }
