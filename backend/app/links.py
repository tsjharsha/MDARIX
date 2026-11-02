"""Where a link MDARIX sends opens (quality plan stage 6): one helper for every server-sent target and e-mail link.

A target names a place, not a string: ``{"section", "tab", "record", "panel"}``. Every screen that opens something
from the server (Readiness checks, Oversight rows, an event's checklist, the trial story's chapters) gets it as
``opens.target``; beside it stay ``opens.section`` and ``opens.tab`` (the tab carrying the record, as
``Reports?complaint=<id>``), which the screens read until 0.10.66, so a tab opened before an upgrade keeps working.
The browser turns a target into an address with one resolver (frontend/src/app/linkTable.ts ``placeOf``); an e-mail
gets the address itself from ``app_path``.

The places, their tabs and the parameter that names each kind of record mirror frontend/src/app/linkTable.json
(the API image carries no frontend files); tests/test_link_targets.py holds the two to the same values and checks that
every server source names a screen and tab that exist, and records that exist.
"""

from __future__ import annotations

import urllib.parse

# Each workspace screen's address (linkTable.json "places").
PATHS = {
    "Getting started": "/app/getting-started",
    "Readiness": "/app/readiness",
    "My Work": "/app/my-work",
    "Complaints": "/app/complaints",
    "Signals": "/app/signals",
    "Investigations": "/app/investigations",
    "Records": "/app/records",
    "Import data": "/app/import-data",
    "My Account": "/app/account",
    "Share feedback": "/app/feedback",
    "Look ahead": "/app/look-ahead",
    "Next steps": "/app/next-steps",
}

# Where each kind of record opens, and the parameter that names it there (linkTable.json "records").
RECORDS = {
    "complaint": ("Readiness", "Oversight", "event"),
    "report": ("Complaints", "Reports", "report"),
    "communication": ("Complaints", "Communications", "communication"),
    "disposition": ("Complaints", "Dispositions", "complaint"),
    "capa": ("Records", "Effectiveness checks", "capa"),
    "case": ("Investigations", "Workspace", "case"),
    "signal": ("Signals", "Signal inbox", "signal"),
    "request": ("My Work", "Evidence requests", "request"),
}


def _param(kind: str, section: str, tab: str | None) -> str:
    """A record's parameter: its own on its own place (a complaint's checklist: ``event``), else its kind's name (a
    complaint's reports: ``Reports?complaint=<id>``)."""
    home_section, home_tab, param = RECORDS[kind]
    return param if (section, tab) == (home_section, home_tab) else kind


def target(
    section: str | None = None,
    tab: str | None = None,
    *,
    record: tuple[str, object] | None = None,
    panel: str | None = None,
) -> dict:
    """Where a link opens: ``{"section", "tab", "target": {...}}``. With only a record, its own place."""
    if record is not None:
        kind, ref = record
        if kind not in RECORDS:
            raise ValueError(f"No place for a {kind!r} record")
        if section is None:
            section, tab = RECORDS[kind][0], RECORDS[kind][1]
        record_ref = {"kind": kind, "id": str(ref)}
    else:
        record_ref = None
    if section not in PATHS:
        raise ValueError(f"No such workspace screen: {section!r}")
    legacy = tab
    if record_ref and record_ref["kind"] != "case":
        query = urllib.parse.urlencode({_param(record_ref["kind"], section, tab): record_ref["id"]})
        legacy = f"{tab or ''}?{query}"
    return {
        "section": section,
        "tab": legacy,
        "target": {"section": section, "tab": tab, "record": record_ref, "panel": panel},
    }


def app_path(section: str, tab: str | None = None, *, record: tuple[str, object] | None = None) -> str:
    """The address of a place, for an e-mail (the browser's address scheme, frontend workspaceAddress.ts): the case
    page names its case and step (``/app/investigations?case=INV000147&step=Decision``); any other screen its tab and
    record (``/app/complaints?tab=Reports&complaint=<id>``)."""
    if section not in PATHS:
        raise ValueError(f"No such workspace screen: {section!r}")
    params: dict[str, str] = {}
    if section == "Investigations":
        if record is not None:
            params["case"] = str(record[1])
        if tab and tab != "All investigations":
            params["step"] = tab
    else:
        if tab:
            params["tab"] = tab
        if record is not None:
            params[_param(record[0], section, tab)] = str(record[1])
    query = urllib.parse.urlencode(params)
    return f"{PATHS[section]}{'?' + query if query else ''}"
