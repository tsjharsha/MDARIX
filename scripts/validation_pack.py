"""B6b B5: write the per-release validation pack (MDX-VAL-004 to -012) into docs/validation/releases/<release>/.

    python scripts/validation_pack.py --release 0.11.04 --junit artifacts/release-checks/junit.xml \
        --release-checks artifacts/release-checks-0.11.04.json
    python scripts/validation_pack.py --release 0.11.04 --junit <file> --dry-run --out artifacts/validation-pack-dryrun

The release identity is an argument and must equal VERSION: a mismatch refuses the pack (exit 1, nothing written; owner
decision O16), except in a dry run, where it is a warning. Every failing traceability or deviation check is listed and the pack is not written (exit 1); with
--dry-run the pack is written anyway, marked "development results, not validation evidence", and the exit code is
still 1 when a check fails. A release folder holding a signed approval is never overwritten (exit 2).

    python scripts/validation_pack.py --release 0.11.04 --oq-protocol

writes only the OQ protocol (MDX-VAL-007-P) and prints its SHA-256: the quality approver signs it before execution
and its signatures.csv row names that SHA-256 in content_sha256 (sha256 is the signed PDF's). Outside a dry run no OQ results are written without that row (O20).
The row is checked, not trusted: a named quality approver (Srinivas T.) with that role, and the signed PDF stored with
the row's SHA-256. Executed rows (executed-results.csv, pq-record.csv) are checked against it: named people, executed
after the approval and not by the approver, evidence IDs that resolve to files in evidence/.

    python scripts/validation_pack.py --release 0.11.04 --update-counts

rewrites the generated counts in MDX-VAL-000 section 3.4 and MDX-VAL-001 section 16.1; a stale block is a check
failure. --author names who runs the generator (default: the git author); anyone but a named person is a check failure."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from validation import pack, pytest_requirements  # noqa: E402

GENERATOR_FILES = ("validation/pack.py", "scripts/validation_pack.py", "validation/pytest_requirements.py")
COUNT_DOCUMENTS = ("README.md", "MDX-VAL-001_VALIDATION_MASTER_PLAN.md")  # MDX-VAL-000 and MDX-VAL-001


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
    parser.add_argument("--results", type=Path, help="executed IQ/OQ results CSV; default <out>/executed-results.csv")
    parser.add_argument("--clock-check", type=Path, help="a clock-check JSON from scripts/clock_check.py")
    parser.add_argument("--commit", default="", help="default: the current commit")
    parser.add_argument("--tag", default="", help="the release tag, when there is one")
    parser.add_argument("--date", default="", help="document date YYYY-MM-DD; default: the commit's date")
    parser.add_argument("--out", type=Path, help="default: docs/validation/releases/<release>")
    parser.add_argument("--dry-run", action="store_true", help="write the pack even when checks fail; marked as such")
    parser.add_argument("--oq-protocol", action="store_true", help="write only the OQ protocol for approval (O20)")
    parser.add_argument(
        "--author", default="", help="who runs the generator (Srinivas T. / Sriharsha T.); default: git author"
    )
    parser.add_argument(
        "--evidence", type=Path, help="evidence files named by ID; default: evidence/ beside the results CSV"
    )
    parser.add_argument("--pq-record", type=Path, help="the MDARIX PQ record; default <out>/pq-record.csv")
    parser.add_argument(
        "--update-counts", action="store_true", help="rewrite the generated counts in MDX-VAL-000 and -001"
    )
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
    sources = pack.Sources(
        requirements=pack.read_requirements(docs / "requirements.csv"),
        scenarios=pack.read_register(docs / "scenario-register.md"),
        tests=pack.read_junit(args.junit) if args.junit else [],
        release_checks=json.loads(args.release_checks.read_text(encoding="utf-8-sig")) if args.release_checks else None,
        release_checks_raw=args.release_checks.read_bytes() if args.release_checks else None,
        junit_raw=args.junit.read_bytes() if args.junit else None,
        junit_meta=pack.read_junit_meta(args.junit) if args.junit else None,
        deviations=pack.read_deviations(docs / "deviation-log.csv"),
        clock_check=json.loads(args.clock_check.read_text(encoding="utf-8")) if args.clock_check else None,
        oq_expected=pack.read_oq_expected(docs / "oq-expected-results.csv"),
        pq_steps=pack.read_pq_steps(docs / "MDX-VAL-008_PQ_PROTOCOL.md"),
        rule_versions=pack.read_rule_register(root / "backend" / "app" / "rule_register" / "data"),
        signatures=pack.read_signatures(docs / "signatures.csv"),
        # the generator that runs (this script's repository), whatever --root holds the sources
        environment={"generator": {name: hashlib.sha256((ROOT / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
                                   for name in GENERATOR_FILES if (ROOT / name).is_file()}},
        count_documents={name: (docs / name).read_text(encoding="utf-8") for name in COUNT_DOCUMENTS
                         if (docs / name).is_file()},
    )  # fmt: skip
    if args.update_counts:  # rating-4 finding 9: counts in the documents are generated, never typed
        block = pack.counts_block(sources)
        for name in COUNT_DOCUMENTS:
            raw = (docs / name).read_bytes().decode("utf-8")
            text = pack.with_counts(raw.replace("\r\n", "\n"), block)
            (docs / name).write_bytes((text.replace("\n", "\r\n") if "\r\n" in raw else text).encode("utf-8"))
            print(f"counts updated in {docs / name}")
        return 0
    version_file = (root / "VERSION").read_text(encoding="utf-8").strip() if (root / "VERSION").exists() else ""
    if args.release != version_file:
        said = f"release {args.release} differs from VERSION {version_file or '(missing)'}"
        if not args.dry_run:  # B6b owner decision O16: a release pack names the release that VERSION says
            print(f"REFUSED: {said}; set VERSION at the release join, then generate the pack.", file=sys.stderr)
            return 1
        print(f"WARNING: {said}; the release identity is set at the release join.", file=sys.stderr)
    tree = pytest_requirements.tree_state(root)[1]
    if tree != "clean":  # owner, 12 Nov 2026: a pack describes committed code only
        if not args.dry_run:
            print(f"REFUSED: the working tree is {tree}; commit or discard the changes first.", file=sys.stderr)
            return 1
        print(f"WARNING: the working tree is {tree}; a dry run only.", file=sys.stderr)
    if pack.signed(out, args.release, docs / "signatures.csv"):
        print(f"REFUSED: {out} holds a signed release approval; a correction is a new version.", file=sys.stderr)
        return 2
    results = args.results or out / "executed-results.csv"
    if results.exists():  # executed IQ/OQ results, fed into the documents, never typed into them
        sources.executed, sources.executed_raw = pack.read_results(results), results.read_bytes()
    sources.evidence = pack.read_evidence(args.evidence or results.parent / "evidence")
    pq = args.pq_record or out / "pq-record.csv"
    if pq.exists():  # the MDARIX PQ record (MDX-VAL-008 section 5), checked and summarised in the VSR
        sources.pq_record, sources.pq_raw = pack.read_pq_record(pq), pq.read_bytes()
    commit = args.commit or _git("rev-parse", "--short=8", "HEAD") or "unknown"
    author = args.author or _git("log", "-1", "--format=%an")
    scripted, _ = pack.oq_tables(sources)
    protocol_sha = pack.protocol_sha256(scripted)
    sources.oq_approval = pack.protocol_approval(sources.signatures, args.release, protocol_sha, root)
    approved = sources.oq_approval.approved
    ctx = pack.Context(
        release=args.release, version_file=version_file, commit=commit, tag=args.tag,
        date=args.date or _git("show", "-s", "--format=%cs", commit) or "1970-01-01", dry_run=args.dry_run,
        head=pack.migration_head(root / "infrastructure" / "database" / "migrations" / "versions"),
        author=author,
        problems=pack.check(sources, args.release)
        + pack.release_check_problems(sources.release_checks, commit, bool(sources.tests))
        + pack.junit_binding_problems(sources.junit_meta, commit)
        + pack.author_problems(author)
        + sources.oq_approval.problems
        + ([] if approved or args.oq_protocol else [
            f"OQ protocol {pack.PROTOCOL_ID} {args.release} is not approved: no signatures.csv row with content_sha256 "
            f"{protocol_sha}; no OQ results without an approved protocol (owner decision O20)"])
        + ([] if approved or not any(r.get("step", "").startswith("OQ-") for r in sources.executed) else [
            "executed-results.csv holds OQ results but the OQ protocol is not approved (owner decision O20)"]),
        oq_approved=approved,
    )  # fmt: skip
    if args.oq_protocol:
        files, sha = pack.build_protocol(ctx, sources)
        pack.write(out, files)
        print(f"Written the OQ protocol to {out}; SHA-256 {sha}. Sign it, then add its signatures.csv row "
              f"({pack.PROTOCOL_ID},{args.release},...,<signed PDF sha256>,{sha}) before execution.")  # fmt: skip
        return 0
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
