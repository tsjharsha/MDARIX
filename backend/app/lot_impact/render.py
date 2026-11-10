"""The lot impact list as a PDF (reports/pdf.py, as the report worksheets and guides) and as CSV rows, from the screen's
view of one list (the signed snapshot, or the list now): the case, the factor, the totals and units by country, each
lot with its complaints, units released, shipped and in stock and the genealogy behind it, the lots left out with the
reason, and the signature manifestation (21 CFR 11.50: the printed name, the date and time, the meaning)."""

from __future__ import annotations

import io

from backend.app.lot_impact.service import NEVER_DECIDES, NOT_IMPORTED

CSV_FIELDS = (
    "record",
    "lot",
    "product",
    "version",
    "group",
    "complaints",
    "complaints_per_1000_units",
    "units_released",
    "units_shipped",
    "units_in_stock",
    "consignee",
    "consignee_type",
    "consignee_reference",
    "country",
    "units",
    "ship_date",
    "evidence",
    "exclusion_reason",
)
PRACTICE = "Practice record"


def group(row: dict) -> str:
    if row["excluded"]:
        return "Left out"
    return "With complaints" if row["complaints"] else "Without complaints yet"


def _number(value) -> str:
    return "-" if value is None else f"{value:,}"


def csv_rows(view: dict) -> list[dict]:
    """One row per shipment of each lot; a lot without distribution gets one row saying so."""
    record = PRACTICE if view.get("practice_label") else ""
    out = []
    for row in view["list"]["lots"]:
        base = {
            "record": record,
            "lot": row["lot_identifier"],
            "product": row["product"] or "",
            "version": row["version"] or "",
            "group": group(row),
            "complaints": row["complaints"],
            "complaints_per_1000_units": "" if row["per_1000"] is None else row["per_1000"],
            "units_released": "" if row["released"] is None else row["released"],
            "units_shipped": "" if row["shipped"] is None else row["shipped"],
            "units_in_stock": "" if row["in_stock"] is None else row["in_stock"],
            "evidence": "; ".join(row["evidence"]),
            "exclusion_reason": row["exclusion_reason"] or "",
        }
        if not row["shipments"]:
            out.append({**base, "consignee": NOT_IMPORTED})
            continue
        for shipment in row["shipments"]:
            out.append(
                {
                    **base,
                    "consignee": shipment["consignee"],
                    "consignee_type": shipment["consignee_type"] or "",
                    "consignee_reference": shipment["consignee_reference"] or "",
                    "country": shipment["country"],
                    "units": shipment["units"],
                    "ship_date": shipment["ship_date"],
                }
            )
    return out


def header_lines(view: dict, organization: str | None) -> list[str]:
    factor = view["list"]["factor"]
    lines = [
        f"Organization: {organization or '-'}",
        f"Investigation: {view['investigation']['business_id'] or view['investigation']['id']}",
        f"Suspect factor ({factor['kind_label'].lower()}): {factor['label']}",
        f"List: {view['which_label']}",
    ]
    if view.get("practice_label"):
        lines.append(view["practice_label"])
    return lines


def _lot_lines(row: dict) -> list[tuple[str, str]]:
    if not row["complaints"]:
        complaints = "no complaints yet"
    else:
        rate = f", {row['per_1000']} per 1,000 units released" if row["per_1000"] is not None else ""
        complaints = f"{row['complaints']} complaint{'' if row['complaints'] == 1 else 's'}{rate}"
    out = [(f"{row['lot_identifier']}  {row['product'] or '-'} {row['version'] or ''}: {complaints}", "body")]
    if row["distribution_imported"]:
        stock = f", {_number(row['in_stock'])} in stock" if row["in_stock"] is not None else ""
        countries = ", ".join(f"{item['country']} {item['units']:,}" for item in row["by_country"])
        out.append(
            (
                f"    {_number(row['released'])} released, {_number(row['shipped'])} shipped{stock} ({countries})",
                "muted",
            )
        )
        if row["over_shipped"]:
            out.append(("    More units shipped than released: check the distribution or the lot's quantity.", "muted"))
        for shipment in row["shipments"]:
            kind = f" ({shipment['consignee_type']})" if shipment["consignee_type"] else ""
            out.append(
                (
                    f"    {shipment['ship_date']}  {shipment['country']}  {shipment['consignee']}{kind}: "
                    f"{shipment['units']:,}",
                    "muted",
                )
            )
    else:
        out.append((f"    {_number(row['released'])} released; {NOT_IMPORTED.lower()}", "muted"))
    for line in row["evidence"]:
        out.append((f"    {line}", "muted"))
    if row["excluded"]:
        out.append((f"    Left out: {row['exclusion_reason']}", "muted"))
    return out


def manifestation(view: dict) -> list[str]:
    signature = view.get("signature") if view["which"] == "signed" else None
    if not signature:
        return ["Not signed: this is the list as the records show it now."]
    lines = [
        f"Signed by {signature['signer_name']} ({signature['signer_role']}) on {signature['signed_at']}.",
        f"Meaning: {signature['meaning']}",
        f"Signature record: {signature['record_business_id'] or signature['record_id']}.",
        f"Content checksum (SHA-256 of the list): {signature['content_fingerprint']}",
    ]
    if view.get("changed"):
        lines.append("Changed since signed: " + "; ".join(view.get("changes") or []) + ".")
    return lines


def lines(view: dict) -> list[tuple[str, str]]:
    listed = view["list"]
    totals = listed["totals"]
    countries = ", ".join(f"{item['country']} {item['units']:,}" for item in totals["by_country"]) or "-"
    out: list[tuple[str, str]] = [(NEVER_DECIDES, "body"), ("", "body"), ("Totals", "heading")]
    out += [
        (
            f"{totals['lots']} lots: {totals['with_complaints']} with complaints ({totals['complaints']} complaints), "
            f"{totals['without_complaints']} without complaints yet; {totals['excluded']} left out.",
            "body",
        ),
        (
            f"Units released {_number(totals['released'])}; shipped {_number(totals['shipped'])}; in stock "
            f"{_number(totals['in_stock'])}"
            + (f"; {totals['not_imported']} lots with distribution not imported" if totals["not_imported"] else "")
            + ".",
            "body",
        ),
        (f"Units shipped by country: {countries}", "body"),
    ]
    for title, rows in (
        ("Lots with complaints", [row for row in listed["lots"] if not row["excluded"] and row["complaints"]]),
        (
            "Lots without complaints yet",
            [row for row in listed["lots"] if not row["excluded"] and not row["complaints"]],
        ),
        ("Lots left out", [row for row in listed["lots"] if row["excluded"]]),
    ):
        if not rows:
            continue
        out += [("", "body"), (title, "heading")]
        for row in rows:
            out += _lot_lines(row)
    out += [("", "body"), ("Signature", "heading"), *((line, "body") for line in manifestation(view))]
    return out


def render_pdf(view: dict, organization: str | None) -> bytes:
    from reports import pdf

    watermark = (
        "PRACTICE RECORD - NOT YOUR REGULATORY RECORD"
        if view.get("practice_label")
        else "MDARIX LISTS - YOU DECIDE ANY FIELD ACTION"
    )
    ref = view["investigation"]["business_id"] or view["investigation"]["id"]
    footer = f"{ref} - lot impact list - MDARIX recommends no field action"
    return pdf.render(
        "MDARIX lot impact list", header_lines(view, organization), lines(view), watermark=watermark, footer=footer
    )


def render_csv(view: dict) -> bytes:
    from backend.app import csv_safe

    stream = io.StringIO()
    writer = csv_safe.writer(stream, fieldnames=list(CSV_FIELDS))
    writer.writeheader()
    writer.writerows(csv_rows(view))
    return stream.getvalue().encode("utf-8-sig")
