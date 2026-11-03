"""Load the published code lists (0.10.77, Release C part C5) from the publishers' own files, never typed in.

The files and their provenance are in ``data/code_lists/manifest.json``: list, version, file, SHA-256, source and
publication date. Four lists:

- ``IMDRF``: IMDRF's adverse event terminology, Annexes A to G of one release, from IMDRF's own workbook (one sheet
  per annex) into ``imdrf_codes``, with each term's status as the file states it ("Retired (2025)", "Not selectable").
- ``FDA_CDRH``: FDA's CDRH adverse event codes (device problem, health effects, component, type of investigation,
  findings, conclusion), each with FDA's own IMDRF code: FDA's published FDA-IMDRF mapping (NCI EVS, the file FDA's
  "MDR Adverse Event Codes" page points to).
- ``FDA_PRODUCT_CODE``: FDA's product classification database (foiclass), each product code with its device name,
  class, review panel and regulation number.
- ``EMDN``: the European Medical Device Nomenclature, the European Commission's file, versioned.

GMDN is licensed and never loaded: each product keeps the organization's own GMDN code. ISO 3166 country codes are
already in MDARIX (trial/business_imports.COUNTRY_CODES).

    python scripts/load_code_lists.py                    # dry run: check every file, say what would change
    python scripts/load_code_lists.py --apply            # load them
    python scripts/load_code_lists.py --only EMDN --apply

Every file is checked whole first (its SHA-256 against the manifest, its columns, codes present and unique, every
parent in the file); a file with a problem is refused and nothing of it is loaded. Each list loads in one transaction.
Nothing is ever deleted: a code already loaded that a file leaves out refuses the file (a new version is loaded as a
new version, and the old one stays, so old reports keep their codes). Loading the same file again changes nothing.
Run it as the database owner (the runtime role only reads the codes).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

MANIFEST = ROOT / "data" / "code_lists" / "manifest.json"
ANNEXES = ("A", "B", "C", "D", "E", "F", "G")
LISTS = ("IMDRF", "FDA_CDRH", "FDA_PRODUCT_CODE", "EMDN")
CDRH_COLUMNS = (
    "NCIt Subset Code",
    "CDRH Subset Name",
    "NCIt Concept Code",
    "NCIt Preferred Term",
    "NCIt Definition",
    "CDRH Preferred Term",
    "CDRH Source Code",
    "CDRH Definition",
    "IMDRF Code",
)
# The CDRH subsets and the IMDRF annex each one codes (the file's own subset names).
CDRH_SUBSETS = {
    "Medical Device Problem": "A",
    "Cause Investigation - Type of Investigation": "B",
    "Cause Investigation - Investigation Findings": "C",
    "Cause Investigation - Investigation Conclusion": "D",
    "Health Effects - Clinical Signs and Symptoms or Conditions": "E",
    "Health Effects - Health Impact": "F",
    "Medical Device Component": "G",
}
PRODUCT_COLUMNS = ("REVIEW_PANEL", "PRODUCTCODE", "DEVICENAME", "DEVICECLASS", "REGULATIONNUMBER")
_IMDRF_CODE = re.compile(r"^[A-G]\d{2,12}$")
_EMDN_CODE = re.compile(r"^[A-Z](\d{2})*$")


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _row(code, term, definition=None, parent=None, status=None, note=None, **extra) -> dict:
    return {
        "code": code,
        "term": term,
        "definition": definition or None,
        "parent_code": parent or None,
        "status": status or None,
        "status_note": note or None,
        **extra,
    }


def _unique(rows: list[dict], key, problems: list[str], what: str) -> None:
    seen: set = set()
    for item in rows:
        value = key(item)
        if value in seen:
            problems.append(f"{what} {value}: appears twice")
        seen.add(value)


def _parents(rows: list[dict], problems: list[str], what: str) -> None:
    codes = {item["code"] for item in rows}
    problems += [
        f"{what} {item['code']}: parent {item['parent_code']} is not in the file"
        for item in rows
        if item["parent_code"] and item["parent_code"] not in codes
    ]


# --- IMDRF: the annexes workbook ------------------------------------------------------------------------------


def parse_imdrf(raw: bytes) -> tuple[str | None, dict[str, list[dict]], list[str]]:
    """(the release, each annex's codes, every problem found). The workbook has one sheet per annex, named A to G:
    a heading ("Release Number: 2026"), then a header row with the level terms, Code, Definition, Status, Status
    Description and CodeHierarchy."""
    from backend.app.trial.xlsx import Workbook, XlsxError

    try:
        book = Workbook(raw)
    except XlsxError as exc:
        return None, {}, [str(exc)]
    problems: list[str] = []
    releases: set[str] = set()
    annexes: dict[str, list[dict]] = {}
    with book:
        names = {sheet.name.strip().upper(): sheet for sheet in book.sheets}
        for annex in ANNEXES:
            sheet = names.get(annex)
            if sheet is None:
                problems.append(f"Annex {annex}: no sheet named {annex}")
                continue
            rows = book.rows(sheet)
            header = next((i for i, r in enumerate(rows) if r and r[0].strip().lower().startswith("level 1")), None)
            for line in rows[: header or 0]:
                if line and line[0].startswith("Release Number:"):
                    releases.add(line[0].split(":", 1)[1].strip())
            if header is None:
                problems.append(f"Annex {annex}: no header row (Level 1 Term ... Code)")
                continue
            head = [cell.strip() for cell in rows[header]]
            missing = [name for name in ("Code", "Definition", "Status", "CodeHierarchy") if name not in head]
            if missing:
                problems.append(f"Annex {annex}: missing column(s) {', '.join(missing)}")
                continue
            at = {name: head.index(name) for name in ("Code", "Definition", "Status", "CodeHierarchy")}
            note_at = head.index("Status Description") if "Status Description" in head else None
            codes: list[dict] = []
            for number, line in enumerate(rows[header + 1 :], start=header + 2):
                cells = line + [""] * (len(head) - len(line))
                code = cells[at["Code"]].strip()
                if not any(cells):
                    continue
                if not _IMDRF_CODE.match(code) or not code.startswith(annex):
                    problems.append(f"Annex {annex} row {number}: '{code}' is not an Annex {annex} code")
                    continue
                term = next((cell.strip() for cell in cells[: at["Code"]] if cell.strip()), "")
                if not term or len(term) > 300:
                    problems.append(f"Annex {annex} {code}: no term, or a term over 300 characters")
                chain = [part.strip() for part in cells[at["CodeHierarchy"]].split("|") if part.strip()]
                if chain and chain[-1] != code:
                    problems.append(f"Annex {annex} {code}: its hierarchy ends with {chain[-1]}")
                codes.append(
                    _row(
                        code,
                        term,
                        cells[at["Definition"]].strip(),
                        chain[-2] if len(chain) > 1 else None,
                        cells[at["Status"]].strip(),
                        cells[note_at].strip() if note_at is not None else None,
                        _root=chain[0] if chain else code,
                    )
                )
            if not codes:
                problems.append(f"Annex {annex}: no codes")
            codes = _primary(codes, problems, annex)
            _unique(codes, lambda item: item["code"], problems, f"Annex {annex}")
            _parents(codes, problems, f"Annex {annex}")
            annexes[annex] = codes
    if len(releases) != 1:
        problems.append(f"the sheets name {len(releases)} releases ({', '.join(sorted(releases)) or 'none'}), not one")
    return (releases.pop() if len(releases) == 1 else None), annexes, problems


def _primary(codes: list[dict], problems: list[str], annex: str) -> list[dict]:
    """One row per code. Annex E lists some terms again under a second heading (E0102 "Brain Injury" under E01 Nervous
    System and E20 Injury, with the same code); the code's own place is the heading its code starts with, and that row
    carries IMDRF's latest wording. A code repeated with no single own place is a problem."""
    by_code: dict[str, list[dict]] = {}
    for item in codes:
        by_code.setdefault(item["code"], []).append(item)
    out = []
    for code, rows in by_code.items():
        if len(rows) == 1:
            out.append(rows[0])
            continue
        if len({tuple(item[k] for k in ("term", "definition", "parent_code", "status")) for item in rows}) == 1:
            out.append(rows[0])  # the same term under two headings
            continue
        own = [item for item in rows if item["_root"] == code[:3]]
        if len(own) != 1:
            problems.append(f"Annex {annex} {code}: appears {len(rows)} times with no single own place")
            continue
        out.append(own[0])
    for item in out:
        item.pop("_root", None)
    return out


# --- FDA: the CDRH codes with their IMDRF codes ---------------------------------------------------------------


def parse_fda_cdrh(raw: bytes) -> tuple[list[dict], list[str]]:
    """FDA's CDRH terminology (tab-separated, NCI EVS): each code with its subset, term, definition and IMDRF code."""
    text = raw.decode("utf-8-sig", errors="strict")
    reader = csv.reader(io.StringIO(text), delimiter="\t")
    head = next(reader, [])
    if tuple(cell.strip() for cell in head) != CDRH_COLUMNS:
        return [], [f"the header is not FDA's CDRH terminology columns: {head[:3]}"]
    rows: list[dict] = []
    problems: list[str] = []
    for number, line in enumerate(reader, start=2):
        if not any(cell.strip() for cell in line):
            continue
        if len(line) != len(CDRH_COLUMNS):
            problems.append(f"line {number}: {len(line)} columns, not {len(CDRH_COLUMNS)}")
            continue
        cells = dict(zip(CDRH_COLUMNS, (cell.strip() for cell in line)))
        subset, code, imdrf = cells["CDRH Subset Name"], cells["CDRH Source Code"], cells["IMDRF Code"]
        if subset not in CDRH_SUBSETS:
            problems.append(f"line {number}: unknown subset '{subset}'")
            continue
        if not code.isdigit():
            problems.append(f"line {number}: FDA code '{code}' is not a number")
            continue
        imdrf_code = imdrf.removeprefix("IMDRF:") if imdrf else ""
        if imdrf and (not _IMDRF_CODE.match(imdrf_code) or imdrf_code[0] != CDRH_SUBSETS[subset]):
            problems.append(f"line {number}: FDA {code}: IMDRF code '{imdrf}' is not in Annex {CDRH_SUBSETS[subset]}")
            continue
        term = cells["CDRH Preferred Term"] or cells["NCIt Preferred Term"]
        if not term:
            problems.append(f"line {number}: FDA {code}: no term")
            continue
        rows.append(
            _row(
                code,
                term,
                cells["CDRH Definition"] or cells["NCIt Definition"],
                subset=subset,
                imdrf_code=imdrf_code or None,
                details={"ncit": cells["NCIt Concept Code"]},
            )
        )
    _unique(rows, lambda item: (item["subset"], item["code"]), problems, "FDA code")
    if not rows and not problems:
        problems.append("the file has no codes")
    return rows, problems


# --- FDA: product classification --------------------------------------------------------------------------------


def parse_fda_product_codes(raw: bytes) -> tuple[list[dict], list[str]]:
    """FDA's product classification file (foiclass.zip or its foiclass.txt, pipe-separated)."""
    if raw[:2] == b"PK":
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                names = [name for name in archive.namelist() if name.lower().endswith("foiclass.txt")]
                if len(names) != 1 or archive.getinfo(names[0]).file_size > 50 * 1024 * 1024:
                    return [], ["the zip does not hold one foiclass.txt"]
                raw = archive.read(names[0])
        except zipfile.BadZipFile:
            return [], ["the file is not a readable zip"]
    text = raw.decode("cp1252")
    reader = csv.reader(io.StringIO(text), delimiter="|", quoting=csv.QUOTE_NONE)
    head = [cell.strip().upper() for cell in next(reader, [])]
    missing = [name for name in PRODUCT_COLUMNS if name not in head]
    if missing:
        return [], [f"missing column(s): {', '.join(missing)}"]
    at = {name: head.index(name) for name in head}
    rows: list[dict] = []
    problems: list[str] = []
    for number, line in enumerate(reader, start=2):
        if not any(cell.strip() for cell in line):
            continue
        cells = line + [""] * (len(head) - len(line))
        code = cells[at["PRODUCTCODE"]].strip().upper()
        if not re.fullmatch(r"[A-Z]{3}", code):
            problems.append(f"line {number}: product code '{code}' is not three letters")
            continue
        name = cells[at["DEVICENAME"]].strip()
        if not name:
            problems.append(f"line {number}: {code}: no device name")
            continue
        details = {
            "device_class": cells[at["DEVICECLASS"]].strip() or None,
            "review_panel": cells[at["REVIEW_PANEL"]].strip() or None,
            "regulation_number": cells[at["REGULATIONNUMBER"]].strip() or None,
        }
        if "SUBMISSION_TYPE_ID" in at:
            details["submission_type_id"] = cells[at["SUBMISSION_TYPE_ID"]].strip() or None
        rows.append(
            _row(code, name[:500], cells[at["DEFINITION"]].strip() if "DEFINITION" in at else None, details=details)
        )
    _unique(rows, lambda item: item["code"], problems, "product code")
    if not rows and not problems:
        problems.append("the file has no product codes")
    return rows, problems


# --- EMDN -----------------------------------------------------------------------------------------------------


def parse_emdn(raw: bytes) -> tuple[str | None, list[dict], list[str]]:
    """(the version, its codes, the problems): the Commission's workbook, a title row ("EMDN_v.2026") then CATEGORY,
    CATEGORY DESCRIPTION, CODE, TERM, LEVEL, TERMINAL LEVEL. A code's parent is the code two characters shorter (the
    category letter for a level-2 code)."""
    from backend.app.trial.xlsx import Workbook, XlsxError

    try:
        with Workbook(raw) as book:
            lines = book.rows(book.sheets[0])
    except XlsxError as exc:
        return None, [], [str(exc)]
    header = next((i for i, r in enumerate(lines) if r and "CODE" in [c.strip().upper() for c in r]), None)
    if header is None:
        return None, [], ["no header row with CODE"]
    title = " ".join(cell for row in lines[:header] for cell in row if cell)
    found = re.search(r"v\.?\s?(\d{4}(?:\.\d+)?)", title)
    head = [cell.strip().upper() for cell in lines[header]]
    term_at = next((i for i, name in enumerate(head) if name.startswith("TERM")), None)
    if term_at is None or "LEVEL" not in head:
        return None, [], ["missing column(s): TERM, LEVEL"]
    code_at, level_at = head.index("CODE"), head.index("LEVEL")
    terminal_at = next((i for i, name in enumerate(head) if name.startswith("TERMINAL")), None)
    rows: list[dict] = []
    problems: list[str] = []
    for number, line in enumerate(lines[header + 1 :], start=header + 2):
        cells = line + [""] * (len(head) - len(line))
        code = cells[code_at].strip().upper()
        if not code:
            continue
        if not _EMDN_CODE.match(code) or len(code) > 30:
            problems.append(f"row {number}: '{code}' is not an EMDN code")
            continue
        term = cells[term_at].strip()
        if not term or len(term) > 500:
            problems.append(f"row {number}: {code}: no term, or a term over 500 characters")
            continue
        level = cells[level_at].strip()
        expected = str((len(code) + 1) // 2)
        if level != expected:
            problems.append(f"row {number}: {code}: level {level}, its length says {expected}")
        parent = None if len(code) == 1 else code[:-2] if len(code) > 3 else code[0]
        rows.append(
            _row(
                code,
                term,
                parent=parent,
                details={
                    "level": int(level) if level.isdigit() else None,
                    "terminal": (cells[terminal_at].strip().upper() == "YES") if terminal_at is not None else None,
                },
            )
        )
    _unique(rows, lambda item: item["code"], problems, "EMDN code")
    _parents(rows, problems, "EMDN code")
    if not rows and not problems:
        problems.append("the file has no codes")
    return (found.group(1) if found else None), rows, problems


# --- Loading ----------------------------------------------------------------------------------------------------


def _changes(existing: dict, rows: list[dict], key, fields) -> tuple[list[dict], list[tuple], list[str]]:
    """(rows new to the database, (row, loaded item) pairs that differ, keys loaded but left out of the file)."""
    fresh, changed = [], []
    wanted = set()
    for item in rows:
        wanted.add(key(item))
        loaded = existing.get(key(item))
        if loaded is None:
            fresh.append(item)
        elif any(getattr(loaded, name) != item.get(name) for name in fields):
            changed.append((item, loaded))
    dropped = sorted(str(value) for value in set(existing) - wanted)
    return fresh, changed, dropped


_IMDRF_FIELDS = ("term", "definition", "parent_code", "status", "status_note")
_REFERENCE_FIELDS = ("term", "definition", "parent_code", "imdrf_code", "status", "details")


def load_imdrf(db, release: str, annexes: dict[str, list[dict]], apply: bool, now: datetime) -> dict:
    from backend.app.db.models.regulatory_reference import ImdrfCode

    summary: dict = {}
    for annex, rows in annexes.items():
        existing = {
            item.code: item
            for item in db.query(ImdrfCode).filter(ImdrfCode.release == release, ImdrfCode.annex == annex).all()
        }
        fresh, changed, dropped = _changes(existing, rows, lambda item: item["code"], _IMDRF_FIELDS)
        if dropped:
            raise SystemExit(f"Not loaded: Annex {annex} of release {release} leaves out loaded codes {dropped[:10]}")
        summary[annex] = {"rows": len(rows), "new": len(fresh), "changed": len(changed)}
        if apply:
            for item, loaded in changed:
                for name in _IMDRF_FIELDS:
                    setattr(loaded, name, item[name])
            db.add_all(
                ImdrfCode(release=release, annex=annex, loaded_at=now, **{k: item[k] for k in ("code", *_IMDRF_FIELDS)})
                for item in fresh
            )
    return summary


def load_reference(db, name: str, version: str, rows: list[dict], apply: bool, now: datetime) -> dict:
    from backend.app.db.models.regulatory_reference import ReferenceCode

    existing = {
        (item.subset, item.code): item
        for item in db.query(ReferenceCode).filter(ReferenceCode.list == name, ReferenceCode.version == version)
    }
    key = lambda item: (item.get("subset") or "", item["code"])  # noqa: E731
    fresh, changed, dropped = _changes(existing, rows, key, _REFERENCE_FIELDS)
    if dropped:
        raise SystemExit(f"Not loaded: {name} {version} leaves out loaded codes {dropped[:10]}")
    if apply:
        for item, loaded in changed:
            for field in _REFERENCE_FIELDS:
                setattr(loaded, field, item.get(field))
        db.add_all(
            ReferenceCode(
                list=name,
                version=version,
                subset=item.get("subset") or "",
                code=item["code"],
                loaded_at=now,
                **{field: item.get(field) for field in _REFERENCE_FIELDS},
            )
            for item in fresh
        )
    return {"rows": len(rows), "new": len(fresh), "changed": len(changed)}


def check(entry: dict, raw: bytes) -> tuple[str | None, object, list[str]]:
    """(the version the file states, its parsed codes, its problems) for one manifest entry."""
    problems = [] if sha256(raw) == entry["sha256"] else [f"SHA-256 {sha256(raw)} is not the manifest's"]
    name = entry["list"]
    if name == "IMDRF":
        version, codes, found = parse_imdrf(raw)
    elif name == "FDA_CDRH":
        codes, found = parse_fda_cdrh(raw)
        version = entry["version"]
    elif name == "FDA_PRODUCT_CODE":
        codes, found = parse_fda_product_codes(raw)
        version = entry["version"]
    elif name == "EMDN":
        version, codes, found = parse_emdn(raw)
    else:
        return None, None, [f"unknown list {name}"]
    problems += found
    if version != entry["version"]:
        problems.append(f"the file states version {version}, the manifest {entry['version']}")
    return version, codes, problems


def run(db, entries: list[dict], folder: Path, apply: bool, out=print) -> int:
    """Check every entry, then (with ``apply``) load each list in its own transaction. 0 when all is well."""
    from backend.app.db.models.regulatory_reference import CodeListFile

    status = 0
    for entry in entries:
        raw = (folder / entry["file"]).read_bytes()
        version, codes, problems = check(entry, raw)
        label = f"{entry['list']} {entry['version']} ({entry['file']})"
        if problems:
            status = 1
            out(f"REFUSED {label}: {len(problems)} problem(s)")
            for problem in problems[:20]:
                out(f"  problem: {problem}")
            continue
        now = datetime.now(timezone.utc)
        if entry["list"] == "IMDRF":
            summary = load_imdrf(db, version, codes, apply, now)
            rows = sum(item["rows"] for item in summary.values())
            detail = "; ".join(
                f"Annex {k} {v['rows']} ({v['new']} new, {v['changed']} changed)" for k, v in summary.items()
            )
        else:
            summary = load_reference(db, entry["list"], version, codes, apply, now)
            rows = summary["rows"]
            detail = f"{rows} codes ({summary['new']} new, {summary['changed']} changed)"
        recorded = (
            db.query(CodeListFile.id)
            .filter(
                CodeListFile.list == entry["list"],
                CodeListFile.version == version,
                CodeListFile.sha256 == entry["sha256"],
            )
            .first()
        )
        if apply:
            if recorded is None:
                db.add(
                    CodeListFile(
                        list=entry["list"],
                        version=version,
                        file_name=entry["file"],
                        source_url=entry["source_url"],
                        published=entry["published"],
                        sha256=entry["sha256"],
                        rows=rows,
                        loaded_at=now,
                    )
                )
            db.commit()
        out(
            f"{'LOADED' if apply else 'CHECKED'} {label}: {detail}. Source: {entry['source_url']}, {entry['published']}"
        )
    if not apply and status == 0:
        out("Dry run: nothing was written. Add --apply to load.")
    return status


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument("--only", choices=LISTS, action="append", help="load only this list (repeatable)")
    parser.add_argument("--apply", action="store_true", help="load (without it: a dry run, nothing written)")
    args = parser.parse_args(argv)
    entries = [item for item in json.loads(args.manifest.read_text(encoding="utf-8"))["files"]]
    if args.only:
        entries = [item for item in entries if item["list"] in args.only]
    from backend.app.db.session import SessionLocal

    db = SessionLocal()
    try:
        print(f"Database: {db.bind.url.host}:{db.bind.url.port}/{db.bind.url.database}")
        return run(db, entries, args.manifest.parent, args.apply)
    finally:
        db.rollback()
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
