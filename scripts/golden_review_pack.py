"""The golden dataset review pack: everything a reviewer needs to sign off the AI release gate's test set, on paper.

    python scripts/golden_review_pack.py [--out artifacts/golden-dataset-review-pack.md]

The AI release gate needs a named person to sign off the golden dataset (backend/app/ai_release_gate.py). This writes
one readable document from the controlled files themselves: for each of the 15 scenarios, the investigation question,
its evidence, what a good answer must cite and surface, what it must never conclude, and the adversarial checks; then
the statement the reviewer signs and the one command that records it. Reading only; it changes nothing.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SCENARIOS = ROOT / "evaluation" / "scenarios" / "scenario_index.json"
CANONICAL = ROOT / "data" / "golden" / "canonical" / "r1_canonical_golden_dataset.json"
DEFAULT_OUT = ROOT / "artifacts" / "golden-dataset-review-pack.md"
EXCERPT = 280
SIGN_OFF_COMMAND = (
    'python scripts/qualify_ai_golden_dataset.py --human-sign-off --name "First Last" --role "Your role" --confirm'
)


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _cell(value: object) -> str:
    """Text safe inside a Markdown table cell."""
    text = " ".join(str(value or "").split()).replace("|", "/")
    return text if len(text) <= EXCERPT else text[: EXCERPT - 1].rstrip() + "…"


def _list(items, empty: str = "None.") -> list[str]:
    values = [str(item) for item in items or [] if str(item).strip()]
    return [f"- {value}" for value in values] if values else [f"- {empty}"]


def build(scenarios: dict, canonical: dict, lock: dict | None, sign_off: dict | None, now: datetime) -> str:
    """The pack as Markdown (pure: the files are passed in)."""
    from evaluation.release_record import SIGN_OFF_STATEMENT, lock_hashes, sign_off_problem

    investigations = {item["investigation_id"]: item for item in canonical.get("investigations", [])}
    evidence: dict[str, list] = {}
    for item in canonical.get("evidence", []):
        evidence.setdefault(item.get("investigation_id"), []).append(item)
    items = scenarios.get("scenarios", [])
    hashes = lock_hashes(lock) or {}
    issue = sign_off_problem(lock, sign_off)
    lines = [
        "# Golden dataset review pack",
        "",
        f"Generated {now.strftime('%Y-%m-%d %H:%M UTC')} from the controlled files. Synthetic test data only.",
        "",
        "## What you are signing",
        "",
        f"MDARIX's AI may be switched on for a pilot only after it passes all {len(items)} scenarios below with the "
        "contracted model, and after a named person has reviewed and approved them as the test. Review each scenario: "
        "are the expected findings right for its evidence, and is every forbidden conclusion one a careful "
        "investigator would refuse to draw? About two minutes a scenario.",
        "",
        f"- Dataset lock: {lock.get('status') if lock else 'missing'}, change control "
        f"{(lock or {}).get('change_control') or 'none'}",
        f"- Current reviewer on the lock: {(lock or {}).get('reviewer') or 'none'}",
        f"- Human sign-off: {'signed by ' + sign_off['approved_by'] if issue is None else issue}",
        "",
        "| Hash | Value |",
        "| --- | --- |",
        *[f"| {name} | `{value}` |" for name, value in sorted(hashes.items())],
        "",
        "## Scenarios at a glance",
        "",
        "| Scenario | Title | Evidence | Must surface | Must never conclude |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in items:
        surfaced = len(item.get("expected_contradictions") or []) + len(item.get("expected_unknowns") or [])
        lines.append(
            f"| {item['scenario_id']} | {_cell(item.get('title'))} | "
            f"{len(evidence.get(item.get('investigation_id'), []))} | {surfaced} | "
            f"{len(item.get('prohibited_conclusions') or [])} |"
        )
    for item in items:
        case = investigations.get(item.get("investigation_id"), {})
        lines += [
            "",
            f"## {item['scenario_id']}: {item.get('title')}",
            "",
            f"**Purpose.** {item.get('purpose')}",
            "",
            f"**Investigation {item.get('investigation_id')}.** {case.get('question') or 'Question not recorded.'}",
            "",
            "**Evidence the AI sees**",
            "",
            "| Evidence | Title | Quality | What it says |",
            "| --- | --- | --- | --- |",
            *[
                f"| {_cell(row.get('evidence_id'))} | {_cell(row.get('title'))} | {_cell(row.get('quality'))} | "
                f"{_cell(row.get('content'))} |"
                for row in evidence.get(item.get("investigation_id"), [])
            ],
            "",
            "**A good answer cites**",
            "",
            *_list(item.get("expected_evidence")),
            "",
            "**A good answer surfaces these contradictions**",
            "",
            *_list(item.get("expected_contradictions")),
            "",
            "**A good answer names these unknowns**",
            "",
            *_list(item.get("expected_unknowns")),
            "",
            "**It must never conclude**",
            "",
            *_list(item.get("prohibited_conclusions")),
            "",
            "**Acceptance criteria**",
            "",
            *_list(item.get("acceptance_criteria")),
        ]
        adversarial = []
        if item.get("forbidden_output_text"):
            adversarial.append(
                "Prompt injection: the evidence hides an instruction; the answer must never contain "
                + ", ".join(f"`{text}`" for text in item["forbidden_output_text"])
                + "."
            )
        if item.get("personal_data"):
            adversarial.append(
                f"Personal data: {len(item['personal_data'])} synthetic personal details sit in the evidence; none may "
                "reach the model (masking is checked on every request)."
            )
        if item.get("investigator_question"):
            adversarial.append(
                f'Leading question: the investigator asks "{item["investigator_question"]}"; the answer must not '
                "confirm a cause the evidence does not establish."
            )
        if adversarial:
            lines += ["", "**Adversarial check**", "", *[f"- {text}" for text in adversarial]]
        lines += [
            "",
            "**Your review**",
            "",
            "- [ ] The expected citations, contradictions and unknowns are right for this evidence.",
            "- [ ] Every forbidden conclusion is one a careful investigator would refuse to draw.",
            "- [ ] Notes:",
        ]
    lines += [
        "",
        "## Sign-off",
        "",
        f"> {SIGN_OFF_STATEMENT}",
        "",
        "When every scenario is reviewed (and any change has gone through the controlled change procedure in "
        "docs/validation/AI_GOLDEN_DATASET_QUALIFICATION.md), run this yourself with your own name and role, then "
        "commit the file it writes (evaluation/GOLDEN_DATASET_HUMAN_SIGN_OFF.json):",
        "",
        "```bash",
        SIGN_OFF_COMMAND,
        "```",
        "",
        "Nobody signs on someone else's behalf, and a tool or an agent never signs. A changed dataset needs a new "
        "sign-off.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    from evaluation.release_record import LOCK, SIGN_OFF, read

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()
    text = build(_read(SCENARIOS), _read(CANONICAL), read(LOCK), read(SIGN_OFF), datetime.now(timezone.utc))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(f"Review pack written: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
