"""The frontend npm audit gate (scripts/npm_audit_gate.py) lets through only reviewed, unexpired exceptions."""

from __future__ import annotations

import datetime
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("npm_audit_gate", ROOT / "scripts" / "npm_audit_gate.py")
gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate)

TODAY = datetime.date(2026, 11, 18)
PICOMATCH = {
    "name": "picomatch",
    "severity": "high",
    "via": [
        {
            "source": 1247710,
            "name": "picomatch",
            "title": "picomatch vulnerable to ReDoS through single-branch repeated extglobs",
            "url": "https://github.com/advisories/GHSA-fc5q-39xc-vjpf",
            "severity": "high",
        }
    ],
}
VITE = {"name": "vite", "severity": "high", "via": ["picomatch", "tinyglobby"]}
EXCEPTION = {
    "id": "GHSA-fc5q-39xc-vjpf",
    "package": "picomatch",
    "reason": "dev tools only",
    "reviewed_by": "owner",
    "expires": datetime.date(2026, 12, 31),
}


def _report(**vulns):
    return {"auditReportVersion": 2, "vulnerabilities": vulns, "metadata": {}}


def test_the_reviewed_advisory_passes():
    assert gate.problems(_report(picomatch=PICOMATCH, vite=VITE), [EXCEPTION], TODAY) == []


def test_a_different_high_advisory_fails():
    other = {
        "name": "lodash",
        "severity": "high",
        "via": [{"name": "lodash", "severity": "high", "url": "https://github.com/advisories/GHSA-aaaa-bbbb-cccc"}],
    }
    found = gate.problems(_report(picomatch=PICOMATCH, lodash=other), [EXCEPTION], TODAY)
    assert len(found) == 1 and "GHSA-aaaa-bbbb-cccc" in found[0]


def test_the_same_advisory_id_in_another_package_is_not_covered():
    moved = {**PICOMATCH, "via": [{**PICOMATCH["via"][0], "name": "micromatch"}]}
    assert gate.problems(_report(micromatch=moved), [EXCEPTION], TODAY)


def test_an_expired_exception_fails_even_when_the_advisory_is_gone():
    found = gate.problems(_report(picomatch=PICOMATCH), [EXCEPTION], datetime.date(2027, 1, 1))
    assert any("expired" in line for line in found)
    assert any("GHSA-fc5q-39xc-vjpf in picomatch" in line for line in found)
    assert gate.problems(_report(), [EXCEPTION], datetime.date(2027, 1, 1))


def test_an_audit_that_errors_fails():
    assert gate.problems({"error": {"code": "ENOAUDIT"}}, [], TODAY)


def test_the_checked_in_exceptions_are_reviewed_and_expire():
    for exc in gate.load_exceptions():
        assert exc["id"].startswith("GHSA-") and exc["package"], exc
        assert len(exc["reason"]) >= 60 and exc["reviewed_by"], exc["id"]
        assert isinstance(exc["expires"], datetime.date), exc["id"]
