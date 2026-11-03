"""The published code lists in the test database (0.10.77): loaded once from data/code_lists by the real loader."""

import json

from scripts.load_code_lists import MANIFEST, run


def ensure_loaded() -> None:
    """Load every list of the manifest unless its file is recorded as loaded already (the loader is idempotent)."""
    from backend.app.db.models.regulatory_reference import CodeListFile
    from backend.app.db.session import SessionLocal

    entries = json.loads(MANIFEST.read_text(encoding="utf-8"))["files"]
    with SessionLocal() as db:
        loaded = {row[0] for row in db.query(CodeListFile.sha256).all()}
        wanted = [entry for entry in entries if entry["sha256"] not in loaded]
        if wanted:
            assert run(db, wanted, MANIFEST.parent, apply=True, out=lambda _line: None) == 0
