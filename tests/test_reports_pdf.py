"""The PDF writer: every audit event and signature over as many pages as it takes, every character as written in the
embedded Inter and Noto Sans Devanagari fonts (0.10.62, J17), hashes in a fixed-width font, and long header and
footer lines wrapped instead of cut (J42)."""

import re
import struct
import uuid
import zlib

from reports import pdf, ttf
from reports.pdf import page_count, text_of
from reports.service import generate_report
from regulatory_intelligence.estar import generate_estar_package

# Characters the writer printed as "?" before 0.10.62: units, symbols, currencies, names.
SAMPLE = "≤ 25 °C, 5 μL ± 0.5, 10 µg, OrbitCare™, €, ₹ 1,25,000, •, …, José, Søren, रमेश, ‘quotes’ – dash"


def _events(count):
    return [
        {
            "id": str(uuid.uuid4()),
            "action": "DECISION_SIGNED" if index % 2 else "EVIDENCE_LINKED",
            "entity_id": str(uuid.uuid4()),
            "actor_ref": f"user-{index}",
            "reason": "Reviewed (all) evidence \\ backslash",
            "details": {"note": "x" * 300},
        }
        for index in range(count)
    ]


def test_every_audit_event_and_signature_is_in_a_multi_page_pdf():
    events = _events(200)
    signatures = [{"signature_id": str(uuid.uuid4()), "valid": True, "decision": "APPROVE"} for _ in range(30)]
    result = generate_report(
        "AUDIT_APPROVAL",
        str(uuid.uuid4()),
        context={"audit_events": events, "signature_verification": signatures, "data_cut_off": "2026-10-05T00:00:00"},
        output_format="PDF",
        tenant_name="Acme Care",
    )
    content = result["content"]
    assert content.startswith(b"%PDF-1.4") and content.rstrip().endswith(b"%%EOF")
    assert page_count(content) > 1
    shown = text_of(content)
    for event in events:
        assert event["id"] in shown
    for signature in signatures:
        assert signature["signature_id"] in shown
    # Parentheses and backslashes are glyph numbers like any other character: they cannot break out of a PDF string.
    assert "Reviewed (all) evidence \\ backslash" in shown
    assert "Data cut-off: 2026-10-05T00:00:00" in shown and "Acme Care" in shown
    assert "Page 1 of" in shown


def test_a_small_report_is_one_page():
    result = generate_report("DECISION_BRIEF", "tenant-a", context={"summary": {"decisions": 1}}, output_format="PDF")
    assert page_count(result["content"]) == 1


def test_the_estar_preparation_pdf_still_renders_its_sections():
    import io
    import zipfile

    package = generate_estar_package(
        tenant_id="tenant-a",
        title="510(k) preparation",
        sections=[
            {"claim_id": "A1", "text": "Claim text", "citation_ids": ["c1"]},
            {"section_id": "device_description", "content": "A syringe pump.", "status": "COMPLETE"},
        ],
        citations={"verified": [{"citation_id": "c1"}], "rejected": [], "all_verified": True},
    )
    with zipfile.ZipFile(io.BytesIO(package["content"])) as archive:
        content = archive.read("estar-preparation.pdf")
        xml = archive.read("estar-preparation.xml")
    assert content.startswith(b"%PDF") and "A syringe pump." in text_of(content)
    assert b'id="device_description"' in xml


def _render(*body: str, header=(), footer="footer", title="Title") -> bytes:
    return pdf.render(title, list(header), [(line, "body") for line in body], watermark="PRACTICE", footer=footer)


def test_every_character_prints_as_written():
    content = _render(SAMPLE, header=[f"Product: {SAMPLE}"], footer=f"Footer {SAMPLE}", title=f"Title {SAMPLE}")
    shown = text_of(content)
    assert "?" not in shown
    assert shown.count(SAMPLE) >= 2  # the body line and the header line (each fits on one line)
    assert SAMPLE in " ".join(shown.split())  # and the wrapped title and footer read the same


def test_the_fonts_are_embedded_and_map_each_glyph_back_to_its_character():
    content = _render(SAMPLE)
    assert b"/FontFile2" in content and b"+Inter-Regular" in content and b"+NotoSansDevanagari-Regular" in content
    objects = {int(n): body for n, body in re.findall(rb"(\d+) 0 obj\n(.*?)\nendobj\n", content, re.S)}

    def stream(number):
        body = objects[number]
        return zlib.decompress(body[body.index(b"stream\n") + 7 : body.rindex(b"\nendstream")])

    inter, noto = ttf.load("Inter-Regular.ttf"), ttf.load("NotoSansDevanagari-Regular.ttf")
    checked = 0
    for font in (body for body in objects.values() if b"/Subtype /Type0" in body):
        cmap = stream(int(re.search(rb"/ToUnicode (\d+) 0 R", font).group(1))).decode().split("endcodespacerange")[1]
        descendant = objects[int(re.search(rb"/DescendantFonts \[(\d+) 0 R", font).group(1))]
        gid_map = stream(int(re.search(rb"/CIDToGIDMap (\d+) 0 R", descendant).group(1)))
        face = noto if b"Devanagari" in font else inter
        for cid, text in re.findall(r"<([0-9A-F]{4})> <([0-9A-F]+)>", cmap):
            char = bytes.fromhex(text).decode("utf-16-be")
            gid = struct.unpack(">H", gid_map[2 * int(cid, 16) : 2 * int(cid, 16) + 2])[0]
            assert gid == face.glyph(char) and gid != 0, char  # the glyph drawn is that character's own glyph
            checked += 1
    assert checked >= len(set(SAMPLE.replace(" ", ""))) - 1


def test_hashes_are_set_in_a_fixed_width_font_and_text_in_the_sans_font():
    digest = "ab" * 32
    content = _render(f"Content SHA-256: {digest}")
    page = next(
        zlib.decompress(body[body.index(b"stream\n") + 7 : body.rindex(b"\nendstream")])
        for body in re.findall(rb"\d+ 0 obj\n(.*?)\nendobj\n", content, re.S)
        if body.startswith(b"<< /Length")
        and b"/Length1" not in body
        and b"CIDInit" not in body
        and b" Tf " in zlib.decompress(body[body.index(b"stream\n") + 7 : body.rindex(b"\nendstream")])
    )
    assert f"/F4 9 Tf ({digest}) Tj".encode() in page  # Courier
    assert b"/F1 9 Tf <" in page  # Inter, by glyph
    assert f"Content SHA-256: {digest}" in text_of(content)


def test_long_header_and_footer_lines_wrap_instead_of_being_cut():
    header = "Products: " + ", ".join(f"OrbitCare {n} infusion pump" for n in range(1, 9))  # about 230 characters
    footer = "Example Medical Devices Private Limited - management review report - " + "x" * 60
    assert len(header) > 105 and len(footer) > 79
    shown = " ".join(text_of(_render("body", header=[header], footer=footer)).split())
    assert header in shown and footer in shown


def test_aligned_columns_stay_aligned():
    rows = ["Standard     Title                Jurisdiction", "ISO 13485    Quality management   International"]
    content = _render(*rows)
    assert "ISO 13485 Quality management International" in text_of(content)
    page = [
        zlib.decompress(body[body.index(b"stream\n") + 7 : body.rindex(b"\nendstream")])
        for body in re.findall(rb"\d+ 0 obj\n(.*?)\nendobj\n", content, re.S)
        if body.startswith(b"<< /Length") and b"/Length1" not in body
    ]
    starts = [float(x) for text in page for x in re.findall(rb"BT 0.00 g ([\d.]+) [\d.]+ Td", text)]
    column = pdf.MARGIN + 13 * pdf.COLUMN  # "Title" and "Quality management" both start at character 13
    assert starts.count(round(column, 1)) == 2
