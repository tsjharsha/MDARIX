"""B6b owner decision O19: the PDFs the owner signs before the big-bang deploy, generated unsigned.

    python scripts/validation_signing_pdfs.py

writes into docs/validation/signing/:
- MDX-VAL-012-template.pdf: the interim release approval template, whole;
- MDX-VAL-000-section-4.pdf: the header of MDX-VAL-000 and its section 4 (owner decisions in force), with a signature
  block for the owner and the system owner's co-signature (owner decision O30).
Each PDF carries "FOR SIGNATURE - NOT SIGNED" on every page. The signed scan or digitally signed PDF is saved next to
it as *-signed.pdf and listed in signatures.csv with its SHA-256 (MDX-VAL-000 DC-R32 to DC-R36); this script never
overwrites a signed file."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from reports import pdf  # noqa: E402
from validation import docx_render  # noqa: E402

WATERMARK = "FOR SIGNATURE - NOT SIGNED"
OWNER_BLOCK = """
## Signatures (owner decisions O19 and O30)

The system owner co-signs first; the owner signs last.

| Role | Name | Meaning of signature | Signature | Date |
|---|---|---|---|---|
| System owner (co-signs) | Sriharsha Telikicherla, Product & Engineering | I confirm, as system owner, that each decision in this section is implemented or planned as its row states, and I accept them for the system. | | |
| Owner and quality approver | Srinivas Telikicherla, QA/RA | I approve the owner decisions in this section as in force from the big-bang deploy. | | |
"""


def section_4(readme: str) -> str:
    """The header table and change history of MDX-VAL-000 (up to section 1), then section 4, then the owner's block."""
    head = readme.split("\n## 1. ")[0]
    body = "## 4. " + readme.split("\n## 4. ")[1].split("\n## 5. ")[0]
    return head.replace("# MDX-VAL-000 ", "# MDX-VAL-000 section 4: ", 1) + "\n" + body + OWNER_BLOCK


def render(markdown: str, name: str) -> bytes:
    title = markdown.splitlines()[0].lstrip("# ")
    return pdf.render(title, ["For the owner's signature before the big-bang deploy"], docx_render.pdf_lines(markdown),
                      watermark=WATERMARK, footer=f"MDARIX {name} - unsigned")  # fmt: skip


def main() -> int:
    docs = ROOT / "docs" / "validation"
    out = docs / "signing"
    out.mkdir(exist_ok=True)
    jobs = {
        "MDX-VAL-012-template": (docs / "MDX-VAL-012_RELEASE_APPROVAL_TEMPLATE.md").read_text(encoding="utf-8"),
        "MDX-VAL-000-section-4": section_4((docs / "README.md").read_text(encoding="utf-8")),
    }
    for name, markdown in jobs.items():
        if (out / f"{name}-signed.pdf").exists():
            print(f"skipped {name}: a signed copy exists; a change is a new version", file=sys.stderr)
            continue
        (out / f"{name}.pdf").write_bytes(render(markdown, name))
        print(f"written {out / (name + '.pdf')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
