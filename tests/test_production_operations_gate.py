"""scripts/validate_production_operations.py: public health only, a 503 or an unreachable target fails, and alert
configuration is reported from the variables the code really reads (MDARIX_ALERT_WEBHOOK / MDARIX_ALERT_EMAIL)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("ops_gate", ROOT / "scripts" / "validate_production_operations.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def serve(monkeypatch, answers: dict):
    requested = []

    def check_url(base, path):
        requested.append(path)
        return answers.get(path, (404, ""))

    monkeypatch.setattr(gate, "check_url", check_url)
    monkeypatch.setenv("MDARIX_OPERATIONAL_URLS", "https://app.mdarix-ci.test")
    for name in ("MDARIX_ALERT_WEBHOOK", "MDARIX_ALERT_EMAIL", "MDARIX_SCHEDULER_HEARTBEAT_URL"):
        monkeypatch.delenv(name, raising=False)
    return requested


def test_live_and_ok_passes_and_readiness_detail_is_never_requested(monkeypatch, capsys):
    requested = serve(monkeypatch, {"/health/live": (200, "{}"), "/health/status": (200, '{"status":"ok"}')})
    assert gate.main() == 0
    assert "/health/ready" not in requested
    assert "ALERT_DESTINATION = MISSING" in capsys.readouterr().out


def test_degraded_still_serves(monkeypatch, capsys):
    serve(monkeypatch, {"/health/live": (200, "{}"), "/health/status": (200, '{"status":"degraded"}')})
    assert gate.main() == 0
    assert "needs attention" in capsys.readouterr().out


def test_down_fails(monkeypatch):
    serve(monkeypatch, {"/health/live": (200, "{}"), "/health/status": (503, '{"status":"down"}')})
    assert gate.main() == 1


def test_an_unreachable_target_fails(monkeypatch):
    serve(monkeypatch, {"/health/live": (None, "URLError"), "/health/status": (None, "URLError")})
    assert gate.main() == 1


def test_alert_channels_come_from_the_variables_the_code_reads(monkeypatch, capsys):
    serve(monkeypatch, {"/health/live": (200, "{}"), "/health/status": (200, '{"status":"ok"}')})
    monkeypatch.setenv("MDARIX_ALERT_WEBHOOK", "https://hooks.mdarix-ci.test/x")
    monkeypatch.setenv("MDARIX_SCHEDULER_HEARTBEAT_URL", "https://hc.mdarix-ci.test/ping")
    gate.main()
    out = capsys.readouterr().out
    assert "ALERT_DESTINATION = CONFIGURED (webhook)" in out
    assert "SCHEDULER_HEARTBEAT = CONFIGURED" in out
