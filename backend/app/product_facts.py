"""A product's device category (J32, release 0.10.64): what kind of device it is changes which checks and report
fields apply (Help › What MDARIX covers).

``products.device_category`` holds the code; an import or a person may give the plain words ("Single use",
"capital equipment", "SaMD"), which ``category_code`` reads. Null when nobody said.
"""

from __future__ import annotations

import re

IMPLANT, SINGLE_USE, REUSABLE, SOFTWARE, IVD, KIT = "IMPLANT", "SINGLE_USE", "REUSABLE", "SOFTWARE", "IVD", "KIT"
CATEGORY_LABELS = {
    IMPLANT: "Implant",
    SINGLE_USE: "Single-use",
    REUSABLE: "Reusable or capital equipment",
    SOFTWARE: "Software",
    IVD: "In-vitro diagnostic (IVD)",
    KIT: "Kit",
}
CATEGORY_HINT = "Use one of: implant, single-use, reusable (or capital equipment), software, IVD, kit."

_NOT_ALNUM = re.compile(r"[^a-z0-9]+")
_WORDS = {
    IMPLANT: ("implant", "implantable", "implanted"),
    SINGLE_USE: ("single use", "single-use", "disposable", "consumable", "single patient use"),
    REUSABLE: ("reusable", "capital equipment", "capital", "equipment", "reusable or capital equipment", "durable"),
    SOFTWARE: ("software", "samd", "software as a medical device"),
    IVD: ("ivd", "in vitro diagnostic", "in-vitro diagnostic", "in vitro", "in-vitro"),
    KIT: ("kit", "procedure pack", "system or procedure pack"),
}
_CODES = {
    _NOT_ALNUM.sub("", word.lower()): code
    for code, words in _WORDS.items()
    for word in (*words, code, CATEGORY_LABELS[code])
}


def category_code(value) -> str | None:
    """The category code for a code or plain words ("Single use" -> SINGLE_USE), or None when it is none of them."""
    return _CODES.get(_NOT_ALNUM.sub("", str(value or "").lower()))


def category_label(code) -> str | None:
    return CATEGORY_LABELS.get(str(code or ""))
