"""B8 step 1: the Commission's EU MIR 7.3.1 (SB-11252) and MHRA's GB MIR 7.2.1 files, vendored byte-identical with
their SHA-256 and source page. No database."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from lxml import etree

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1] / "data" / "mir_forms"
EU_TYPES = ("Initial", "Followup", "InitialFinal", "FinalRep", "FinalNonRep")


def _manifest() -> dict:
    return json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))


def test_b8_vendored_files_match_their_manifest():
    seen = set()
    for edition in _manifest()["editions"]:
        folder = ROOT / edition["folder"]
        assert edition["page"].startswith(("https://health.ec.europa.eu/", "https://www.gov.uk/"))
        for entry in edition["files"]:
            path = folder / entry["file"]
            assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"], entry["file"]
            assert entry["source_url"] == "member of the zip" or entry["source_url"].startswith(
                ("https://health.ec.europa.eu/document/download/", "https://assets.publishing.service.gov.uk/media/")
            )
            seen.add(path)
        # every file in the folder is pinned: nothing unpinned rides along
        assert set(folder.iterdir()) <= seen, edition["folder"]


def test_b8_each_eu_xsd_loads():
    for kind in (*EU_TYPES, "PDFgeneric"):
        schema = ROOT / "eu-7.3.1-SB-11252" / f"incident-{kind}-v7.3.1.xsd"
        etree.XMLSchema(etree.parse(str(schema)))
        assert b"SB-11252" in schema.read_bytes()


def test_b8_each_gb_xsd_loads():
    for kind in EU_TYPES:
        etree.XMLSchema(etree.parse(str(ROOT / "gb-7.2.1" / f"incident-{kind}GB-v7.2.1.xsd")))
