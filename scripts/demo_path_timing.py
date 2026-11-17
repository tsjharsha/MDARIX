"""Time the WHIF demo path's API calls against a running local backend, and flag server errors and slow calls.

The script starts its own local backend on a mdarix_whif_* demo database or a *_test database (it refuses
anything else), with e-mail delivery and alerts forced off (NO_SEND), for example:

    $env:POSTGRES_DB = "mdarix_whif_demo"
    python scripts/demo_path_timing.py --port 8017 --rounds 20 --out timing.md

It signs a new trial up, approves it as a Platform Administrator (a session minted for an existing PLATFORM_ADMIN test
account), signs in as the trial owner and walks the nine story steps: each read is repeated --rounds times, each write
runs once (writes change the trial). Every call is checked for a 5xx; p95 is held to the owner's SLOs (read 500 ms,
write 1 s). Exit code 1 when any call answered 5xx or went over its limit.
"""

from __future__ import annotations

import argparse
import math
import os
from datetime import datetime, timedelta, timezone
import subprocess
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
        if response.status_code >= 400 and method != "GET":
            print(f"{self.step}: {method} {label or path} -> {response.status_code} {response.text[:200]}")
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


def iso(hours: int = 0) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")


def day(days: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).date().isoformat()


def enroll_authenticator(w: Walk, owner: httpx.Client) -> str:
    """Set up the trial owner's authenticator through the API, as a person does, so the walk can sign."""
    from auth import totp

    started = w.call(owner, "POST", "/api/v1/auth/mfa/enroll")
    assert started.status_code == 200, started.text
    secret = started.json()["secret"]
    done = w.call(owner, "POST", "/api/v1/auth/mfa/verify-enrollment", json={"code": totp.current_code(secret)})
    assert done.status_code == 200, done.text
    return secret


def next_code(secret: str) -> str:
    """The code of the next 30-second step: accepted once the current one was used (each code works once)."""
    from auth import totp

    return totp.code_at(secret, totp._step() + 1)


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
    secret = enroll_authenticator(w, owner)

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
        json={
            "classification": "COMPLAINT",
            "seen_version": event["version"],
            "password": PASSWORD,
            "mfa_code": next_code(secret),
        },
    )
    assert signed.status_code == 200, signed.text
    complaint = signed.json().get("complaint_id")
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
        # Relative to the sample's day 0 (today): what was known an hour ago.
        params={"temporal_mode": "known", "as_of": iso(hours=-1), "retrieval_top_k": 8},
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
    w.read(owner, "/api/v1/reviews/audit-trail", params={"from": day(-7), "to": day(0)})
    w.read(owner, "/api/v1/governance/signed-records")
    w.read(owner, "/api/v1/admin/audit-chain")

    w.step = "9 admin AI"
    w.read(admin, "/api/v1/platform-admin/ai/models")
    w.read(admin, "/api/v1/platform-admin/console/ai-activity")
    w.read(admin, f"{org}/ai-metrics", "/trial-organizations/{id}/ai-metrics")


# Settings the backend and this script run with, whatever the developer's dotenv file holds: no e-mail, no alert
# webhook or alert e-mail. python-dotenv never replaces a variable that is present, so an empty value keeps it out.
NO_SEND = {
    "MDARIX_EMAIL_DELIVERY": "off",
    "MDARIX_SMTP_HOST": "",
    "MDARIX_SMTP_USERNAME": "",
    "MDARIX_SMTP_PASSWORD": "",
    "MDARIX_ALERT_WEBHOOK": "",
    "MDARIX_ALERT_FALLBACK_WEBHOOK": "",
    "MDARIX_ALERT_EMAIL": "",
}


def checked_database(database: str) -> str:
    """A WHIF demo database (mdarix_whif_*) or a *_test database other than the shared ones; anything else refused."""
    if database.startswith("mdarix_whif_"):
        from scripts.demo_database import guard

        return guard(database)
    if not database.endswith("_test") or database in ("mdarix_r1_test",):
        raise SystemExit(
            f"Refusing: POSTGRES_DB must name a mdarix_whif_* or *_test database other than mdarix_r1_test, "
            f"not {database!r}"
        )
    return database


def backend_env(database: str) -> dict[str, str]:
    return {**os.environ, **NO_SEND, "POSTGRES_DB": database, "PYTHONPATH": str(ROOT)}


def start_backend(database: str, port: int) -> subprocess.Popen:
    """Start the local backend this walk times, with NO_SEND forced on, and wait for /health."""
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.app.main:app", "--port", str(port), "--no-access-log"],
        cwd=ROOT,
        env=backend_env(database),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        if server.poll() is not None:
            raise SystemExit(f"The backend stopped at start (exit code {server.returncode})")
        try:
            if httpx.get(f"http://127.0.0.1:{port}/health", timeout=2).status_code == 200:
                return server
        except httpx.HTTPError:
            pass
        time.sleep(1)
    server.terminate()
    raise SystemExit("The backend did not answer /health within 120 s")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=8017, help="local port for the backend this script starts")
    parser.add_argument("--rounds", type=int, default=20, help="repeats of each read (default 20)")
    parser.add_argument("--out", help="also write the results table to this Markdown file")
    args = parser.parse_args()
    database = checked_database(os.environ.get("POSTGRES_DB", ""))
    os.environ.update(NO_SEND)  # this process reads the database too; it must not send either
    server = start_backend(database, args.port)
    w = Walk(f"http://127.0.0.1:{args.port}", args.rounds)
    try:
        walk(w)
    finally:
        server.terminate()
        server.wait(timeout=30)
        table, ok = w.table()
        print(table)
        if args.out:
            Path(args.out).write_text(table + "\n", encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
