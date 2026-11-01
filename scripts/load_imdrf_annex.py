"""Load one annex of one IMDRF adverse event terminology release into ``imdrf_codes`` (G2a).

The codes come only from IMDRF's own published files; none are typed in here. Save the annex as a CSV with a header
row naming at least ``code`` and ``term`` (``definition`` and ``parent_code`` are read when present), then:

    python scripts/load_imdrf_annex.py --release 2026 --annex A annex_a.csv           # check only
    python scripts/load_imdrf_annex.py --release 2026 --annex A annex_a.csv --apply   # load
    ... --apply --replace                                                             # reload a loaded annex

The whole file is checked first (codes present and unique, terms present, every parent code in the file) and loaded
in one transaction, or not at all. Run it as the database owner (the runtime role may only read the codes).
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ANNEXES = ("A", "B", "C", "D", "E", "F", "G")


def parse_annex(text: str) -> tuple[list[dict], list[str]]:
    """The annex's codes, and every problem found (an empty list means the file can be loaded)."""
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    headers = {name.strip().lower(): name for name in (reader.fieldnames or [])}
    problems = [f"missing column: {column}" for column in ("code", "term") if column not in headers]
    if problems:
        return [], problems
    codes: list[dict] = []
    seen: set[str] = set()
    for line, row in enumerate(reader, start=2):
        value = {
            column: (row.get(headers[column]) or "").strip() if column in headers else ""
            for column in ("code", "term", "definition", "parent_code")
        }
        if not value["code"]:
            problems.append(f"line {line}: no code")
            continue
        if len(value["code"]) > 20 or len(value["term"]) > 300:
            problems.append(f"line {line}: {value['code']}: code or term too long")
        if not value["term"]:
            problems.append(f"line {line}: {value['code']}: no term")
        if value["code"] in seen:
            problems.append(f"line {line}: {value['code']}: appears twice")
        seen.add(value["code"])
        codes.append(value)
    problems += [
        f"{item['code']}: parent {item['parent_code']} is not in the file"
        for item in codes
        if item["parent_code"] and item["parent_code"] not in seen
    ]
    if not codes and not problems:
        problems.append("the file has no codes")
    return codes, problems


def dropped_codes(loaded: set[str], codes: list[dict]) -> list[str]:
    """Codes already loaded that the new file leaves out: mappings people approved may point at them."""
    return sorted(loaded - {item["code"] for item in codes})


def load(db, release: str, annex: str, codes: list[dict], replace: bool) -> int:
    from backend.app.db.models.regulatory_reference import ImdrfCode

    existing = db.query(ImdrfCode).filter(ImdrfCode.release == release, ImdrfCode.annex == annex)
    loaded = {code for (code,) in existing.with_entities(ImdrfCode.code).all()}
    if loaded:
        if not replace:
            raise SystemExit(f"Annex {annex} of release {release} is already loaded; add --replace to reload it.")
        dropped = dropped_codes(loaded, codes)
        if dropped:
            # A reload may correct terms and add codes, never remove one a mapping may use; a new release does that.
            raise SystemExit(f"Not loaded: the new file leaves out loaded codes {', '.join(dropped)}.")
        existing.delete(synchronize_session=False)
    now = datetime.now(timezone.utc)
    db.add_all(
        ImdrfCode(
            release=release,
            annex=annex,
            code=item["code"],
            term=item["term"],
            definition=item["definition"] or None,
            parent_code=item["parent_code"] or None,
            loaded_at=now,
        )
        for item in codes
    )
    db.commit()
    return len(codes)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("file", type=Path)
    parser.add_argument("--release", required=True)
    parser.add_argument("--annex", required=True, choices=[*ANNEXES, *(a.lower() for a in ANNEXES)])
    parser.add_argument("--apply", action="store_true", help="load the codes (without it, only check the file)")
    parser.add_argument("--replace", action="store_true", help="replace an annex already loaded for this release")
    args = parser.parse_args(argv)
    release, annex = args.release.strip(), args.annex.upper()
    if not release or len(release) > 20:
        parser.error("--release must be 1 to 20 characters")
    codes, problems = parse_annex(args.file.read_text(encoding="utf-8"))
    for problem in problems:
        print(f"problem: {problem}")
    if problems:
        print(f"Not loaded: {len(problems)} problem(s).")
        return 1
    if not args.apply:
        print(f"Checked: {len(codes)} codes for Annex {annex} of release {release}. Add --apply to load them.")
        return 0
    from backend.app.db.session import SessionLocal

    db = SessionLocal()
    try:
        count = load(db, release, annex, codes, args.replace)
    finally:
        db.close()
    print(f"Loaded {count} codes into Annex {annex} of release {release}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
