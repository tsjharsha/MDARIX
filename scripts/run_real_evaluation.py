"""Run the honest golden evaluation (VS001-VS012) on the real pipeline and save the report.

    python scripts/run_real_evaluation.py [--pause 20] [--out artifacts/real-golden-evaluation.json]

Uses the configured language model (MDARIX_GENAI_*) or, without one, the rule-based pipeline - the report says which.
Nothing is saved to the database.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.db.session import SessionLocal  # noqa: E402
from evaluation.real_pipeline import run_real_golden_suite  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pause", type=float, default=0.0, help="seconds between scenarios (provider rate limits)")
    parser.add_argument("--out", default=str(ROOT / "artifacts" / "real-golden-evaluation.json"))
    args = parser.parse_args()
    db = SessionLocal()
    try:
        report = run_real_golden_suite(db, pause_seconds=args.pause)
    finally:
        db.close()
    report["generated_at"] = datetime.now(timezone.utc).isoformat()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    print(f"{'Scenario':<9}{'Result':<7}{'Author':<16}{'Secs':>6}  Failed checks")
    for result in report["results"]:
        failed = [check["check"] for check in result.get("checks", []) if check["status"] != "PASS"]
        failed = failed or ([result["error"]] if result.get("error") else [])
        author = result.get("analysis_author") or "-"
        print(
            f"{result['scenario_id']:<9}{result['status']:<7}{author:<16}{result.get('seconds', 0):>6}  {', '.join(failed)}"
        )
    print(f"\n{report['passed']}/{report['total']} passed; {report['model_written']} written by the language model.")
    print(
        f"Scenarios that test something specific: {report['passed_with_specific_expectations']}/"
        f"{report['with_specific_expectations']} passed (the rest only show nothing false was claimed)."
    )
    print(f"Report: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
