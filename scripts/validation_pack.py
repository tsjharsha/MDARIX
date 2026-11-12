"""B6b B5: write the per-release validation pack (MDX-VAL-004 to -012) into docs/validation/releases/<release>/.

    python scripts/validation_pack.py --release 0.11.04 --junit artifacts/release-checks/junit.xml \
        --release-checks artifacts/release-checks-0.11.04.json
    python scripts/validation_pack.py --release 0.11.04 --junit <file> --dry-run --out artifacts/validation-pack-dryrun

The release identity is an argument and must equal VERSION: a mismatch refuses the pack (exit 1, nothing written; owner
decision O16), except in a dry run, where it is a warning. Every failing traceability or deviation check is listed and the pack is not written (exit 1); with
--dry-run the pack is written anyway, marked "development results, not validation evidence", and the exit code is
still 1 when a check fails. A release folder holding a signed approval is never overwritten (exit 2)."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from validation import pack  # noqa: E402


def _git(*args: str) -> str:
    try:
        return subprocess.run(
            ["git", "-C", str(ROOT), *args], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--release", required=True, help="release identity, e.g. 0.11.04")
    parser.add_argument("--junit", type=Path, help="pytest JUnit XML of this release (with requirement properties)")
    parser.add_argument("--release-checks", type=Path, help="artifacts/release-checks-<version>.json")
    parser.add_argument("--clock-check", type=Path, help="a clock-check JSON from scripts/clock_check.py")
    parser.add_argument("--commit", default="", help="default: the current commit")
    parser.add_argument("--tag", default="", help="the release tag, when there is one")
    parser.add_argument("--date", default="", help="document date YYYY-MM-DD; default: the commit's date")
    parser.add_argument("--out", type=Path, help="default: docs/validation/releases/<release>")
    parser.add_argument("--dry-run", action="store_true", help="write the pack even when checks fail; marked as such")
    parser.add_argument("--root", type=Path, default=ROOT, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    root = args.root
    docs = root / "docs" / "validation"
    # A dry run never writes into the controlled release folder unless --out says so.
    out = args.out or (
        root / "artifacts" / "validation-pack-dryrun" / args.release
        if args.dry_run
        else docs / "releases" / args.release
    )
    version_file = (root / "VERSION").read_text(encoding="utf-8").strip() if (root / "VERSION").exists() else ""
    if args.release != version_file:
        said = f"release {args.release} differs from VERSION {version_file or '(missing)'}"
        if not args.dry_run:  # B6b owner decision O16: a release pack names the release that VERSION says
            print(f"REFUSED: {said}; set VERSION at the release join, then generate the pack.", file=sys.stderr)
            return 1
        print(f"WARNING: {said}; the release identity is set at the release join.", file=sys.stderr)
    if pack.signed(out, args.release, docs / "signatures.csv"):
        print(f"REFUSED: {out} holds a signed release approval; a correction is a new version.", file=sys.stderr)
        return 2
    sources = pack.Sources(
        requirements=pack.read_requirements(docs / "requirements.csv"),
        scenarios=pack.read_register(docs / "scenario-register.md"),
        tests=pack.read_junit(args.junit) if args.junit else [],
        release_checks=json.loads(args.release_checks.read_text(encoding="utf-8-sig")) if args.release_checks else None,
        release_checks_raw=args.release_checks.read_bytes() if args.release_checks else None,
        deviations=pack.read_deviations(docs / "deviation-log.csv"),
        clock_check=json.loads(args.clock_check.read_text(encoding="utf-8")) if args.clock_check else None,
    )
    commit = args.commit or _git("rev-parse", "--short=8", "HEAD") or "unknown"
    ctx = pack.Context(
        release=args.release, version_file=version_file, commit=commit, tag=args.tag,
        date=args.date or _git("show", "-s", "--format=%cs", commit) or "1970-01-01", dry_run=args.dry_run,
        head=pack.migration_head(root / "infrastructure" / "database" / "migrations" / "versions"),
        problems=pack.check(sources, args.release)
        + pack.release_check_problems(sources.release_checks, commit, bool(sources.tests)),
    )  # fmt: skip
    for problem in ctx.problems:
        print(f"CHECK FAILED: {problem}", file=sys.stderr)
    if ctx.problems and not args.dry_run:
        print(f"{len(ctx.problems)} check(s) failed; nothing written.", file=sys.stderr)
        return 1
    pack.write(out, pack.build(ctx, sources))
    print(f"Written {out} ({'dry run, ' + pack.DEV_BANNER.lower() if args.dry_run else 'for review and signature'})")
    return 1 if ctx.problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
