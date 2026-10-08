"""The image-scan exceptions (.trivyignore.yaml) stay a reviewed list: each says why, and each expires.

CI fails on every HIGH or CRITICAL finding except these; an entry without a reason, or one that would never come back
for review, would quietly widen that.
"""

import datetime
import re
from pathlib import Path

import yaml

IGNORE_FILE = Path(__file__).resolve().parents[1] / ".trivyignore.yaml"
# The longest an exception may stand before it must be reviewed again (from the day it was written or renewed).
MAX_REVIEW_DAYS = 183


def _entries() -> list[dict]:
    return yaml.safe_load(IGNORE_FILE.read_text(encoding="utf-8"))["vulnerabilities"]


def test_every_exception_names_a_finding_says_why_and_expires():
    entries = _entries()
    assert entries, "no reviewed exceptions: remove the file rather than leave it empty"
    ids = [entry["id"] for entry in entries]
    assert len(ids) == len(set(ids)), "an exception is listed twice"
    for entry in entries:
        assert re.fullmatch(r"(CVE-\d{4}-\d{4,}|GHSA-[\w-]+)", entry["id"]), entry
        assert len(entry.get("statement", "").strip()) >= 60, f"{entry['id']}: say why it does not reach MDARIX"
        assert isinstance(entry.get("expired_at"), datetime.date), f"{entry['id']}: give an expiry date (YYYY-MM-DD)"


def test_no_exception_is_set_to_stand_for_more_than_six_months():
    reviewed = re.search(r"Reviewed (\d{4}-\d{2}-\d{2})", IGNORE_FILE.read_text(encoding="utf-8"))
    assert reviewed, "the file says when its exceptions were last reviewed"
    review_day = datetime.date.fromisoformat(reviewed.group(1))
    for entry in _entries():
        assert (entry["expired_at"] - review_day).days <= MAX_REVIEW_DAYS, entry["id"]


def test_the_scans_use_the_reviewed_list_instead_of_ignoring_every_unfixed_finding():
    workflows = Path(__file__).resolve().parents[1] / ".github" / "workflows"
    for name in ("ci.yml", "release.yml"):
        text = (workflows / name).read_text(encoding="utf-8")
        assert "--ignore-unfixed" not in text, name
        assert "--ignorefile /review/.trivyignore.yaml" in text, name
