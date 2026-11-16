"""Time the WHIF demo path's API calls against a running local backend, and flag server errors and slow calls.

Run only against a local backend on a *_test database (the script refuses anything else), for example:

    $env:POSTGRES_DB = "mdarix_demo_test"
    python -m uvicorn backend.app.main:app --port 8017          # in one window
    python scripts/demo_path_timing.py --base-url http://127.0.0.1:8017 --rounds 20 --out timing.md

It signs a new trial up, approves it as a Platform Administrator (a session minted for an existing PLATFORM_ADMIN test
account), signs in as the trial owner and walks the nine story steps: each read is repeated --rounds times, each write
runs once (writes change the trial). Every call is checked for a 5xx; p95 is held to the owner's SLOs (read 500 ms,
write 1 s). Exit code 1 when any call answered 5xx or went over its limit.
"""

from __future__ import annotations

import argparse
import math
import os
import sys
import time
import uuid
from collections import defaultdict
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

READ_MS, WRITE_MS = 500, 1000
PASSWORD = "Demo path timing 2026!"


def p95(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]


class Walk:
    def __init__(self, base: str, rounds: int):
        self.base, self.rounds = base.rstrip("/"), rounds
        self.samples: dict[tuple[str, str, str], list[float]] = defaultdict(list)
        self.statuses: dict[tuple[str, str, str], set[int]] = defaultdict(set)
        self.step = ""

    def call(self, client: httpx.Client, method: str, path: str, label: str | None = None, **kwargs) -> httpx.Response:
        start = time.perf_counter()
        response = client.request(method, self.base + path, **kwargs)
        key = (self.step, method, label or path)
        self.samples[key].append((time.perf_counter() - start) * 1000)
        self.statuses[key].add(response.status_code)
        return response

    def read(self, client, path: str, label: str | None = None, **kwargs) -> httpx.Response:
        response = None
        for _ in range(self.rounds):
            response = self.call(client, "GET", path, label, **kwargs)
        return response

    def table(self) -> tuple[str, bool]:
        lines = [
            "| Step | Call | n | p50 ms | p95 ms | max ms | Limit | Status | Result |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
        ok = True
        for (step, method, label), values in self.samples.items():
            limit = READ_MS if method == "GET" else WRITE_MS
            statuses = sorted(self.statuses[(step, method, label)])
            worst = p95(values)
            bad = [s for s in statuses if s >= 500]
            result = "5xx" if bad else ("OVER" if worst > limit else "ok")
            ok &= result == "ok"
            ordered = sorted(values)
            lines.append(
                f"| {step} | {method} {label} | {len(values)} | {ordered[len(ordered) // 2]:.0f} | {worst:.0f} "
                f"| {limit} | {','.join(map(str, statuses))} | {result} |"
            )
        return "\n".join(lines), ok


def platform_admin_session() -> str:
    """A session for an existing PLATFORM_ADMIN account of the test database (never created here)."""
    from auth.durable import new_session
    from backend.app.db.models.foundation import AuthUser
    from backend.app.db.session import SessionLocal
    from backend.app.db.tenant_scope import bind_system

    with SessionLocal() as db:
        bind_system(db, "demo path timing: platform admin session")
        admin = (
            db.query(AuthUser)
            .filter(AuthUser.role == "PLATFORM_ADMIN", AuthUser.status == "ACTIVE")
            .order_by(AuthUser.created_at)
            .first()
        )
        if admin is None:
            raise SystemExit("No active PLATFORM_ADMIN account in this test database: run the backend tests once first")
        return new_session(db, admin.id, admin.tenant_id)


def activation_token(approval: dict, email: str) -> str:
    if approval.get("activation_path"):
        return parse_qs(urlparse(approval["activation_path"]).query)["token"][0]
    from auth.durable import issue_invitation
    from backend.app.db.models.foundation import AuthUser
    from backend.app.db.session import SessionLocal
    from backend.app.db.tenant_scope import bind_system

    with SessionLocal() as db:
        bind_system(db, "demo path timing: activation")
        user = db.query(AuthUser).filter(AuthUser.username == email).one()
        return issue_invitation(db, user.id, user.tenant_id)


def walk(w: Walk) -> None:
    public, admin, owner = httpx.Client(timeout=60), httpx.Client(timeout=60), httpx.Client(timeout=60)
    admin.cookies.set("mdarix_session", platform_admin_session())

    w.step = "1 sign-up"
    email = f"demo-timing-{uuid.uuid4().hex[:10]}@example.invalid"
    profile = {"job_title": "Quality Lead", "country": "United States", "no_patient_data": True}
    body = {"email": email, "display_name": "Taylor Quality", "organization": "OrbitCare Devices", **profile}
    assert w.call(public, "POST", "/api/v1/auth/signup", json=body).status_code == 200
    items = w.call(admin, "GET", "/api/v1/platform-admin/trial-requests", params={"q": email}).json()["items"]
    request_id = next(item["id"] for item in items if item["email"] == email)
    approval = w.call(
        admin, "POST", f"/api/v1/platform-admin/trial-requests/{request_id}/approve", "/trial-requests/{id}/approve"
    )
    assert approval.status_code == 200, approval.text
    approval = approval.json()
    token = activation_token(approval, email)
    w.call(owner, "POST", "/api/v1/auth/activate-account", json={"token": token, "password": PASSWORD})
    signed_in = w.call(owner, "POST", "/api/v1/auth/signin", json={"email": email, "password": PASSWORD})
    assert signed_in.status_code == 200, signed_in.text
    tenant = approval["tenant_id"]

    w.step = "2 trial orgs"
    org = f"/api/v1/platform-admin/trial-organizations/{tenant}"
    w.read(admin, "/api/v1/platform-admin/trial-organizations/summary")
    w.read(admin, "/api/v1/platform-admin/trial-organizations")
    w.read(admin, org, "/trial-organizations/{id}")
    users = w.read(admin, f"{org}/users/ai-access", "/trial-organizations/{id}/users/ai-access").json()
    w.read(admin, f"{org}/ai-metrics", "/trial-organizations/{id}/ai-metrics")
    first_user = (users.get("items") or users.get("users") or [{}])[0].get("id") if isinstance(users, dict) else None
    if first_user:
        w.call(
            admin,
            "PUT",
            f"{org}/users/{first_user}/ai-access",
            "/trial-organizations/{id}/users/{user}/ai-access",
            json={"active": True, "reason": "Demo: AI on for this trial user"},
        )

    w.step = "3 trial home"
    for path in ("status", "story", "one-story", "short-story", "focus", "feedback", "demo-request"):
        w.read(owner, f"/api/v1/trial/{path}")

    w.step = "4 intake+triage"
    w.read(owner, "/api/v1/intake")
    w.read(owner, "/api/v1/triage", params={"show": "open"})
    answers = {f"Q{n}": {"answer": "NO"} for n in range(1, 10)} | {"Q3": {"answer": "YES"}}
    words = "Caller says the OrbitCare pump alarmed at start-up and would not run."
    event = w.call(
        owner, "POST", "/api/v1/intake", json={"kind": "CONTACT", "reporter_words": words, "answers": answers}
    )
    assert event.status_code in (200, 201), event.text
    event = event.json()
    signed = w.call(
        owner,
        "POST",
        f"/api/v1/intake/{event['id']}/check/sign",
        "/intake/{id}/check/sign",
        json={"classification": "COMPLAINT", "seen_version": event["version"], "password": PASSWORD},
    )
    complaint = signed.json().get("complaint_id") if signed.status_code == 200 else None
    me = w.read(owner, "/api/v1/triage").json()["people"][0]["id"]
    if complaint:
        w.call(
            owner,
            "POST",
            f"/api/v1/triage/COMPLAINT/{complaint}/record",
            "/triage/COMPLAINT/{id}/record",
            json={
                "severity": "NEGLIGIBLE",
                "potential_severity": "MINOR",
                "event_owner": me,
                "triage_owner": me,
                "backup_owner": me,
                "immediate_action": "Out of use.",
            },
        )
    flagship = w.read(owner, "/api/v1/oversight/events/SAMPLE-RV-11", "/oversight/events/{ref}").json()
    sample_complaint = flagship["event"]["complaint_id"]

    w.step = "5 AI"
    w.read(owner, "/api/v1/ai/status")
    resolved = w.read(
        owner,
        "/api/v1/workspace/context/resolve",
        "/workspace/context/resolve",
        params={"investigation": "SAMPLE-INV-001"},
    ).json()
    investigation = resolved["investigation_id"]
    w.call(
        owner,
        "POST",
        "/api/v1/ask/",
        json={"question": "What do we know about the alarms?", "investigation_id": investigation},
    )

    w.step = "6 investigation"
    inv = f"/api/v1/investigations/{investigation}"
    w.read(
        owner,
        f"{inv}/workspace",
        "/investigations/{id}/workspace?as_of",
        params={"temporal_mode": "known", "as_of": "2026-10-01T00:00:00Z", "retrieval_top_k": 8},
    )
    for tail in ("readiness", "decisions", "evidence-inventory", "rca/fishbone", "intelligence/hypotheses"):
        w.read(owner, f"{inv}/{tail}", f"/investigations/{{id}}/{tail}")
    whys = {"problem": "Pressure alarms on the ward", "whys": [{"text": f"Why number {n}"} for n in (1, 2, 3)]}
    w.call(owner, "POST", f"{inv}/rca/five-whys", "/investigations/{id}/rca/five-whys", json=whys)
    cause = {"statement": "Sensor lot drift after the supplier change", "cause_category": "MATERIAL"}
    w.call(owner, "POST", f"{inv}/rca/causes", "/investigations/{id}/rca/causes", json=cause)
    hypothesis = {"statement": "Incoming inspection was reduced after the supplier change"}
    w.call(
        owner, "POST", f"{inv}/intelligence/hypotheses", "/investigations/{id}/intelligence/hypotheses", json=hypothesis
    )
    w.read(owner, f"/api/v1/products/{resolved['product_id']}/investigations", "/products/{id}/investigations")

    w.step = "7 markets+forms"
    w.read(owner, f"/api/v1/complaints/{sample_complaint}/market-assessments", "/complaints/{id}/market-assessments")
    w.read(owner, "/api/v1/complaints/reportability", params={"show": "all", "page_size": 100})
    rv09 = w.read(owner, "/api/v1/oversight/events/SAMPLE-RV-09", "/oversight/events/{ref}").json()["event"]
    reports = w.read(owner, "/api/v1/reports", params={"complaint_id": rv09["complaint_id"]}).json()["items"]
    for report in [item for item in reports if item.get("id")][:1]:
        detail = w.read(owner, f"/api/v1/reports/{report['id']}", "/reports/{id}").json()
        snapshot = (detail.get("approved_snapshot") or {}).get("id")
        if snapshot:
            for form in ("worksheet.pdf", "emdr.xml"):
                w.read(
                    owner,
                    f"/api/v1/reports/{report['id']}/{form}",
                    f"/reports/{{id}}/{form}",
                    params={"snapshot": snapshot},
                )

    w.step = "8 trust"
    w.read(owner, "/api/v1/admin/audit-history")
    w.read(owner, f"{inv}/trust/timeline", "/investigations/{id}/trust/timeline")
    w.read(owner, "/api/v1/reviews/audit-trail", params={"from": "2026-10-05", "to": "2026-10-11"})

    w.step = "9 admin AI"
    w.read(admin, "/api/v1/platform-admin/ai/models")
    w.read(admin, "/api/v1/platform-admin/console/ai-activity")
    w.read(admin, f"{org}/ai-metrics", "/trial-organizations/{id}/ai-metrics")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default="http://127.0.0.1:8017")
    parser.add_argument("--rounds", type=int, default=20, help="repeats of each read (default 20)")
    parser.add_argument("--out", help="also write the results table to this Markdown file")
    args = parser.parse_args()
    database = os.environ.get("POSTGRES_DB", "")
    if not database.endswith("_test") or database in ("mdarix_r1_test",):
        raise SystemExit(
            f"Refusing: POSTGRES_DB must name a *_test database other than mdarix_r1_test, not {database!r}"
        )
    host = urlparse(args.base_url).hostname
    if host not in ("127.0.0.1", "localhost"):
        raise SystemExit("Refusing: the demo path timing runs against a local backend only")
    w = Walk(args.base_url, args.rounds)
    try:
        walk(w)
    finally:
        table, ok = w.table()
        print(table)
        if args.out:
            Path(args.out).write_text(table + "\n", encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
