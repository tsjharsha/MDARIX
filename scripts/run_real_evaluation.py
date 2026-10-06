"""Run the honest golden evaluation (VS001-VS012) on the real pipeline and save the report.

    python scripts/run_real_evaluation.py [--pause 20] [--record] [--out artifacts/real-golden-evaluation.json]
                                          [--gate [--min-passed N] [--require-model]]

Uses the configured language model (MDARIX_GENAI_*) or, without one, the rule-based pipeline - the report says which.
Analyses are not saved; --record saves the evaluation report itself so the Trust page can show it.

--gate makes this a release gate (.github/workflows/ai-evaluation.yml, docs/runbooks/DEPLOYMENT.md): the exit code is
1 unless every scenario with specific expectations passes, at least --min-passed scenarios pass (default: all), and,
with --require-model, every analysis was written by the language model rather than the rules.
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
from evaluation.real_pipeline import record_run, run_real_golden_suite  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pause", type=float, default=0.0, help="seconds between scenarios (provider rate limits)")
    parser.add_argument(
        "--scenario",
        action="append",
        dest="scenarios",
        help="run only this scenario ID; repeat for more than one (for example --scenario VS007)",
    )
    parser.add_argument("--out", default=str(ROOT / "artifacts" / "real-golden-evaluation.json"))
    parser.add_argument("--record", action="store_true", help="save the run for the Trust page")
    parser.add_argument("--gate", action="store_true", help="exit 1 when the run does not meet the release bar")
    parser.add_argument("--min-passed", type=int, default=None, help="scenarios that must pass (default: all)")
    parser.add_argument("--require-model", action="store_true", help="fail when the rules wrote any analysis")
    args = parser.parse_args()
    started = datetime.now(timezone.utc)
    db = SessionLocal()
    try:
        report = run_real_golden_suite(
            db,
            pause_seconds=args.pause,
            scenario_ids={item.upper() for item in args.scenarios} if args.scenarios else None,
        )
        report["generated_at"] = datetime.now(timezone.utc).isoformat()
        if args.record:
            db.rollback()  # the pipeline saved nothing; start the recording cleanly
            print(f"Recorded evaluation run {record_run(db, report, started)}")
    finally:
        db.close()
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
    if args.gate:
        problems = gate_problems(report, args.min_passed, args.require_model)
        for problem in problems:
            print(f"GATE FAILED: {problem}")
        if problems:
            return 1
        print("GATE PASSED")
    return 0


def gate_problems(report: dict, min_passed: int | None, require_model: bool) -> list[str]:
    """Why a run does not meet the release bar (empty when it does)."""
    problems = []
    needed = report["total"] if min_passed is None else min_passed
    if report["passed"] < needed:
        problems.append(f"{report['passed']}/{report['total']} scenarios passed; {needed} required")
    if report["passed_with_specific_expectations"] < report["with_specific_expectations"]:
        problems.append(
            f"{report['passed_with_specific_expectations']}/{report['with_specific_expectations']} scenarios with "
            "specific expectations passed; all are required"
        )
    if require_model and report["model_written"] < report["total"]:
        problems.append(f"only {report['model_written']}/{report['total']} analyses were written by the model")
    return problems


if __name__ == "__main__":
    raise SystemExit(main())
