"""The trial-story refresh lists in counts only for the read-only production run: no trial name or key, no
reference to a trial's own complaints, and never together with --apply."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "refresh_trial_story.py"


def _script():
    spec = importlib.util.spec_from_file_location("refresh_trial_story", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.unit
def test_counts_name_no_trial_and_no_complaint_of_its_own():
    results = [
        {
            "tenant": "acme-medical",
            "name": "Acme Medical Devices Pvt Ltd",
            "result": "would change RT-0042 US draft assessment: due 30 days -> 5 days; would change RT-0043 ...",
            "deadlines": 2,
        },
        {
            "tenant": "acme-medical",
            "name": "Acme Medical Devices Pvt Ltd",
            "result": "would add SAMPLE-CASE-11 and the shipments",
            "sample": ["SAMPLE-CASE-11, the call behind SAMPLE-RV-11, unsigned (0.10.93)", "the shipments (0.10.93)"],
        },
        {"tenant": "other-org", "name": "Other Org", "result": "no sample data (left as it is)"},
    ]
    out = "\n".join(_script().count_lines(results))
    for private in ("acme-medical", "Acme Medical", "other-org", "Other Org", "RT-0042", "RT-0043"):
        assert private not in out
    assert "Trial 1 of 2: 2 deadline-rule change(s)" in out
    assert "Trial 1 of 2: would add 2 sample item(s): SAMPLE-CASE-11" in out
    assert "Trial 2 of 2: no sample data (left as it is)" in out


@pytest.mark.unit
def test_counts_cannot_be_combined_with_apply():
    with pytest.raises(SystemExit):
        _script().main(["--apply", "--counts"])
