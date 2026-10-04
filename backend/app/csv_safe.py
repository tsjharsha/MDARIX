"""CSV exports that spreadsheets open as data, never as formulas.

A cell that starts with ``=``, ``+``, ``-`` or ``@`` (or a tab or carriage return) is run as a formula by Excel,
LibreOffice and Google Sheets when the file is opened, so a record whose name is ``=HYPERLINK(...)`` or
``=cmd|' /C calc'!A0`` would execute on an administrator's machine (CSV injection). ``safe_cell`` prefixes such a
value with an apostrophe, which spreadsheets show as text; ``writer`` is ``csv.DictWriter`` with that applied to
every value. Every CSV MDARIX produces goes through here.
"""

from __future__ import annotations

import csv
from typing import Any

FORMULA_TRIGGERS = ("=", "+", "-", "@", "\t", "\r")


def safe_cell(value: Any) -> Any:
    """``value`` as a cell a spreadsheet treats as text. Non-strings (numbers, None, dates) pass through unchanged:
    the csv module renders them itself and they cannot start with a trigger character."""
    if not isinstance(value, str):
        return value
    if value.startswith(FORMULA_TRIGGERS):
        return "'" + value
    return value


class SafeDictWriter(csv.DictWriter):
    """``csv.DictWriter`` whose every value is passed through ``safe_cell``."""

    def writerow(self, rowdict):  # noqa: D102 - csv.DictWriter contract
        return super().writerow({key: safe_cell(value) for key, value in rowdict.items()})

    def writerows(self, rowdicts):  # noqa: D102 - csv.DictWriter contract
        for rowdict in rowdicts:
            self.writerow(rowdict)


def writer(stream, fieldnames, **kwargs) -> SafeDictWriter:
    """A formula-safe ``DictWriter`` on ``stream`` (same arguments as ``csv.DictWriter``)."""
    return SafeDictWriter(stream, fieldnames=fieldnames, **kwargs)
