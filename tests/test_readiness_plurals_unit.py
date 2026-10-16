"""The readiness summary's sentences count in proper English: "1 record", "2 records" (no "1 records")."""

from __future__ import annotations

from backend.app.readiness_home import summary


def _data(count: int) -> dict:
    return {
        "period": {"from": "2026-01-01", "to": "2026-06-30", "days": 180},
        "readiness": {
            "summary": {"clear": 7, "checks": 8, "critical": 1, "attention": 0, "not_set": 0},
            "checks": [],
        },
        "complaints": {
            "received": count,
            "closed": 0,
            "death": 0,
            "serious_injury": 0,
            "malfunction": count,
            "by_product_version": [],
            "more_groups": count,
        },
        "second_look": {"confirmed": count, "dismissed": 0},
        "reporting": {
            "decisions": count,
            "reported": 0,
            "not_reportable": 0,
            "inside_window": 0,
            "after_window": 0,
            "windows": [],
        },
        "trends": {"signals_by_status": {}, "signals_raised": count, "rising": []},
        "risk_file": {
            "summary": {
                "products": 1,
                "not_reviewed": 1,
                "reassessment_overdue": 0,
                "reassessment_open": 0,
                "no_risk_register": 0,
                "reviewed": 0,
            },
            "products": [
                {
                    "name": "VentraLink 250",
                    "label": "Not reviewed",
                    "complaints": count,
                    "harm": 0,
                    "risk_reviews": count,
                    "risks_assessed": 0,
                    "risks": count,
                    "reassessments_open": count,
                }
            ],
        },
        "capa": {"opened": count, "checks_signed_effective": 0, "checks_signed_not_effective": 0, "now": ""},
        "limitations": [],
    }


def _text(count: int) -> str:
    return "\n".join(text for text, _ in summary.lines(_data(count)))


def test_one_of_a_kind_is_singular():
    text = _text(1)
    assert "and 1 more product version\n" in text
    assert "Second look: 1 record confirmed as complaints" in text
    assert "1 reassessment open." in text
    for wrong in ("1 records", "1 reassessments", "1 more product versions", "1 complaints", "1 risks "):
        assert wrong not in text


def test_several_are_plural():
    text = _text(3)
    assert "and 3 more product versions" in text
    assert "Second look: 3 records confirmed as complaints" in text
    assert "3 reassessments open." in text
