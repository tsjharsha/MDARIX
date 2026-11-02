"""Release 0.10.75's report step for trials made before it (scripts/refresh_trial_story.py), idempotent.

From 0.10.75 (Release C part C3), on the new navigation, signing a market conclusion as reportable creates that
market's report (FDA 3500A for the US, the MvPI MDAE form for India). A trial on the new navigation where someone
signed a reportable US or India conclusion before the upgrade, and never started its worksheet, gets that report now,
as the signing would have made it: prepared by the conclusion's signer, from the signed version, with its deadline.

The sample's own reports (SAMPLE-RV-09 in the US, acknowledged; SAMPLE-RV-10 in India, a correction after a bounced
e-mail) already exist and fit the status path as they are: nothing of theirs changes. A trial on the classic
navigation is left as it is. The caller commits.

From 0.10.76 (C4) the EU / NI, Great Britain and Canada forms join (forms.BY_MARKET), so the same step creates the
report of such a conclusion too: the sample's own SAMPLE-RV-07 (EU / NI, signed reportable by the sample author) gets
its EU MIR worksheet, a sample report prepared by the sample author. A new trial gets it when its sample is staged
(sample_clock.py).
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.app.enterprise_audit import make_audit_event

ACTOR = "system:trial-sample"


def _missing(db: Session, tenant_id) -> list:
    """The signed, current reportable conclusions of a market with a report form, and no report yet."""
    from backend.app.authority_reports import forms
    from backend.app.authority_reports.router import _candidates, new_navigation
    from backend.app.db.models.authority_reports import ReportObligation
    from backend.app.reportability import markets

    if not new_navigation(db, tenant_id):
        return []
    started = {
        (row.complaint_id, row.market)
        for row in db.query(ReportObligation.complaint_id, ReportObligation.market).filter(
            ReportObligation.tenant_id == tenant_id, ReportObligation.kind == "INITIAL"
        )
    }
    return [
        row
        for row in _candidates(db, tenant_id)
        if row.conclusion == markets.REPORTABLE
        and row.market in forms.BY_MARKET
        and not row.filed_on
        and (row.complaint_id, row.market) not in started
    ]


def refresh(db: Session, tenant_id, apply: bool, now: datetime | None = None) -> int:
    """How many reports the trial still needs; with ``apply`` they are created and audited (the caller commits)."""
    from backend.app.authority_reports.router import start

    missing = _missing(db, tenant_id)
    if not apply:
        return len(missing)
    now = now or datetime.now(timezone.utc)
    for signed in missing:
        # The sample's own conclusion (SAMPLE-RV-07's EU, from 0.10.76) gives a sample report.
        obligation = start(
            db,
            tenant_id,
            signed.complaint_id,
            signed.market,
            signed.signed_by,
            now,
            source_system=getattr(signed, "source_system", None),
            candidate=signed,
        )
        db.add(
            make_audit_event(
                tenant_id=tenant_id,
                actor_ref=ACTOR,
                action="REPORT_CREATED_FROM_CONCLUSION",
                entity_type="ReportObligation",
                entity_id=obligation.id,
                details={
                    "complaint_id": str(signed.complaint_id),
                    "market": signed.market,
                    "form": obligation.form_code,
                    "version": signed.version,
                    "refresh": "0.10.75",
                },
                created_at=now,
            )
        )
    db.flush()
    return len(missing)
