"""Draft explanations (rules H-0 to H-5) and challenge questions (C-1 to C-9), rule version 1 (B5 spec 2.3, 2.4).

Pure functions over the facts of one investigation (``facts.read``): the same facts always give the same drafts and
questions. A draft is an explanation to test, never a finding: it is not ranked, scored or given a probability, drafts
come in rule order, and each says which rule drafted it. MDARIX never decides a root cause; a person adopts, judges and
signs. Thresholds live here, in one place, versioned as rule version 1 (owner decision B5-D5), so a later rule register
can take them over.

A fact is ``{"text": str, "records": [{"type", "id", "ref"}]}``: every sentence cites the records behind it.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta

from backend.app.decision_brief import rules as brief_rules
from backend.app.signals.trend_rules import unit_days

RULE_VERSION = 1
# H-2: the top lots hold at least this share of the scope complaints with at most this share of the units; with units
# unknown, at least the same share of complaints in at most this share of the lots.
LOT_COMPLAINT_SHARE, LOT_UNIT_SHARE, LOT_COUNT_SHARE = 0.6, 0.4, 1 / 3
# H-4: at least this share of scope complaints coded No Fault Found or user error; a country holding this share.
USE_CODE_SHARE, COUNTRY_SHARE = 1 / 3, 0.6
# H-0: fewer scope complaints than this cannot test any rule.
MIN_COMPLAINTS = 3
# C-4: a share of complaints without version or lot above this is material; C-8: fewer complaints than this.
UNKNOWN_SHARE_MATERIAL, SMALL_NUMBERS = 0.2, 5
STRONG_WORDS = ("root cause", "proven", "confirmed", "definitely")
# H-4's "you may already have this": a person's hypothesis about use or setting.
USE_TERMS = ("setting", "use error", "user error", "misuse", "environment", "ward", "operator")
DAYS_PER_MONTH = 30.4375
NOT_A_FINDING = "Not a finding."


def label(rule: str) -> str:
    return f"Drafted by rule {rule} v{RULE_VERSION} from your records. {NOT_A_FINDING}"


def question_label(rule: str) -> str:
    return f"Question from rule {rule} v{RULE_VERSION}"


# ------------------------------------------------------------------------------------------------- small helpers


def _rec(kind: str, item: dict) -> dict:
    return {"type": kind, "id": item["id"], "ref": item["ref"]}


def _fact(text: str, records: list[dict] | None = None) -> dict:
    return {"text": text, "records": records or []}


def _n(count: int, one: str, many: str | None = None) -> str:
    return f"{count} {one if count == 1 else (many or one + 's')}"


def _short(ref: str) -> str:
    """A lot's short name: its last part (``SAMPLE-ORBIT-300-LOT-003`` -> ``003``)."""
    return str(ref).rsplit("-", 1)[-1]


def _lot_list(lots: list[dict]) -> str:
    names = [_short(item["ref"]) for item in lots]
    head = "lot" if len(names) == 1 else "lots"
    return f"{head} {', '.join(names[:-1])} and {names[-1]}" if len(names) > 1 else f"{head} {names[0]}"


def _versions_lots(facts: dict, version_ids) -> list[dict]:
    wanted = set(version_ids)
    return sorted((lot for lot in facts["lots"].values() if lot["version_id"] in wanted), key=lambda lot: lot["ref"])


def _exposure(lots: list[dict], start: date | None, end: date) -> float | None:
    """Unit-months in the field over ``start``..``end`` from units released with release dates (trend_rules.unit_days);
    None when a lot's units or release is unknown (never a rate from partial units)."""
    if not lots or start is None or end < start:
        return None
    days = unit_days([(lot["released"], lot["units_released"]) for lot in lots], start, end)
    return days / DAYS_PER_MONTH if days else None


def _rate_text(count: int, exposure: float | None, days: int) -> str:
    if exposure:
        return f"{_n(count, 'complaint')}, {count * 1000 / exposure:.1f} per 1,000 unit-months"
    return f"{_n(count, 'complaint')} in {days} days (units unknown: by calendar days only)"


def _units_unknown(lots: list[dict]) -> list[dict]:
    return [lot for lot in lots if lot["units_released"] is None]


def _all_problem_complaints(facts: dict) -> list[dict]:
    """The scope complaints and the same-problem ones outside the scope on the case's product (shown, never counted
    into the scope)."""
    return [*facts["complaints"], *facts["outside"]]


def _considered(facts: dict) -> list[dict]:
    return [item for item in facts["hypotheses"] if brief_rules.considered(item)]


def _duplicate(facts: dict, rule: str, terms) -> str | None:
    """ "You may already have this": a considered hypothesis adopted from this rule, or one whose statement names any
    of the terms (record IDs, supplier names, words). A hint only; MDARIX never merges them."""
    for item in _considered(facts):
        statement = str(item.get("statement") or "").lower()
        if item.get("draft_rule") == rule or any(term and term.lower() in statement for term in terms):
            return item["business_id"]
    return None


def _draft(facts, rule, key, title, statement, for_, against, missing, terms) -> dict:
    return {
        "rule": rule,
        "rule_version": RULE_VERSION,
        "key": key,
        "label": label(rule),
        "title": title,
        "statement": statement,
        "for": for_,
        "against": against,
        "missing": missing,
        "duplicate_of": _duplicate(facts, rule, terms),
    }


# ---------------------------------------------------------------------------------------------- the draft rules


def h1_changes(facts: dict) -> list[dict]:
    """H-1: a change affecting a component of a scope version took effect before at least one scope complaint."""
    drafts = []
    scope_versions = {v for v, item in facts["versions"].items() if item["in_scope"]}
    as_of = facts["as_of"].date()
    for change in facts["changes"]:
        effective = change["effective_on"]
        affected = set(change["version_ids"]) & scope_versions
        if effective is None or not affected:
            continue
        after = [c for c in facts["complaints"] if c["event_on"] and c["event_on"] >= effective]
        if not after:
            continue
        before_scope = [c for c in facts["complaints"] if c["event_on"] and c["event_on"] < effective]
        changed = [facts["components"][c] for c in change["component_ids"] if c in facts["components"]]
        suppliers = sorted({s["name"] for part in changed for s in part["suppliers"]})
        part = ", ".join(item["name"] for item in changed) or "the whole product"
        on_versions = [c for c in _all_problem_complaints(facts) if c["version_id"] in affected and c["event_on"]]
        lots = _versions_lots(facts, affected)
        first = min((lot["released"] for lot in lots if lot["released"]), default=None)
        before = [c for c in on_versions if c["event_on"] < effective]
        later = [c for c in on_versions if c["event_on"] >= effective]
        for_ = [
            _fact(
                f"On the affected versions, before {change['ref']} took effect ({effective.isoformat()}): "
                f"{_rate_text(len(before), _exposure(lots, first, effective - timedelta(days=1)), max(0, (effective - (first or effective)).days))}; "
                f"after: {_rate_text(len(later), _exposure(lots, effective, as_of), (as_of - effective).days + 1)}.",
                [_rec("change", change)] + [_rec("complaint", c) for c in later],
            )
        ]
        built = [lot for lot in lots if set(lot["genealogy"]) & set(change["component_ids"])]
        with_lot = [c for c in later if c["lot_id"] in {lot["id"] for lot in built}]
        if with_lot:
            for_.append(
                _fact(
                    f"{_n(len(with_lot), 'complaint')} came from {_lot_list(built)}, built with the changed part "
                    "(genealogy).",
                    [_rec("lot", lot) for lot in built] + [_rec("complaint", c) for c in with_lot],
                )
            )
        against = []
        without = [
            c
            for c in _all_problem_complaints(facts)
            if c["version_id"] and c["version_id"] not in change["version_ids"]
        ]
        for version_id, items in sorted(_group(without, "version_id").items()):
            version = facts["versions"].get(version_id)
            if version is None:
                continue
            against.append(
                _fact(
                    f"{_n(len(items), 'complaint')} with the same problem on {version['ref']}, which is not recorded "
                    f"with {part}"
                    + (
                        f" (its parts come from {', '.join(_version_suppliers(facts, version_id))})"
                        if _version_suppliers(facts, version_id)
                        else ""
                    )
                    + ".",
                    [_rec("version", version)] + [_rec("complaint", c) for c in items],
                )
            )
        if before_scope:
            against.append(
                _fact(
                    f"{_n(len(before_scope), 'scope complaint')} happened before {change['ref']} took effect, so the "
                    "change cannot explain them (they count against it, never for it).",
                    [_rec("change", change)] + [_rec("complaint", c) for c in before_scope],
                )
            )
        missing = []
        no_genealogy = [lot for lot in lots if not lot["genealogy"]]
        if no_genealogy:
            missing.append(
                _fact(
                    f"Genealogy (component lots) not imported for {_n(len(no_genealogy), 'lot')}.",
                    [_rec("lot", lot) for lot in no_genealogy],
                )
            )
        if _units_unknown(lots):
            missing.append(
                _fact(
                    f"Units unknown for {_n(len(_units_unknown(lots)), 'lot')}.",
                    [_rec("lot", lot) for lot in _units_unknown(lots)],
                )
            )
        linked = {
            ref
            for entity in [*change["component_ids"], *(s["id"] for p in changed for s in p["suppliers"])]
            for ref in facts["entity_evidence"].get(entity, [])
        }
        if changed and not linked:
            missing.append(_fact(f"No inspection or other evidence is linked to {part} or its supplier."))
        names = f" from {', '.join(suppliers)}" if suppliers else ""
        drafts.append(
            _draft(
                facts,
                "H-1",
                f"H-1:{change['id']}",
                f"Component or supplier change {change['ref']}",
                f"The change {change['ref']} ({part}{names}, effective {effective.isoformat()}) may explain the "
                "complaints that followed it.",
                for_,
                against,
                missing,
                [change["ref"], *suppliers],
            )
        )
    return drafts


def _group(items: list[dict], key: str) -> dict:
    found = defaultdict(list)
    for item in items:
        found[item[key]].append(item)
    return found


def _version_suppliers(facts: dict, version_id: str) -> list[str]:
    version = facts["versions"].get(version_id) or {"components": []}
    return sorted(
        {s["name"] for c in version["components"] for s in facts["components"].get(c, {}).get("suppliers", [])}
    )


def h2_lots(facts: dict) -> list[dict]:
    """H-2: the top lots hold at least 60% of the scope complaints with at most 40% of the units (units unknown: at
    least 60% of complaints in at most a third of the lots)."""
    complaints = facts["complaints"]
    with_lot = [c for c in complaints if c["lot_id"] in facts["lots"]]
    if not with_lot:
        return []
    versions = {facts["lots"][c["lot_id"]]["version_id"] for c in with_lot}
    lots = _versions_lots(facts, versions)
    counts = Counter(c["lot_id"] for c in with_lot)
    ordered = sorted(lots, key=lambda lot: (-counts.get(lot["id"], 0), lot["ref"]))
    top, held = [], 0
    for lot in ordered:
        if held >= LOT_COMPLAINT_SHARE * len(complaints):
            break
        top.append(lot)
        held += counts.get(lot["id"], 0)
    if held < LOT_COMPLAINT_SHARE * len(complaints):
        return []
    unknown = _units_unknown(lots)
    total_units = sum(lot["units_released"] or 0 for lot in lots)
    if not unknown and total_units:
        top_units = sum(lot["units_released"] for lot in top)
        if top_units > LOT_UNIT_SHARE * total_units:
            return []
        # Named: every lot with more than its share of complaints for its units (the top lots among them).
        named = [
            lot for lot in ordered if counts.get(lot["id"], 0) / len(with_lot) > lot["units_released"] / total_units
        ]
    else:
        if len(top) > LOT_COUNT_SHARE * len(lots):
            return []
        named = top
    for_ = []
    for lot in ordered:
        n = counts.get(lot["id"], 0)
        if not n:
            continue
        rate = f", {n * 1000 / lot['units_released']:.1f} per 1,000 units released" if lot["units_released"] else ""
        cited = [c for c in with_lot if c["lot_id"] == lot["id"]]
        for_.append(
            _fact(
                f"Lot {_short(lot['ref'])}: {_n(n, 'complaint')}{rate}.",
                [_rec("lot", lot)] + [_rec("complaint", c) for c in cited],
            )
        )
    shared = (
        set.intersection(*(set(lot["genealogy"]) for lot in named))
        if named and all(lot["genealogy"] for lot in named)
        else set()
    )
    for component_id in sorted(shared):
        part = facts["components"].get(component_id)
        if part:
            for_.append(
                _fact(
                    f"{_lot_list(named).capitalize()} share the part {part['name']} (genealogy).",
                    [_rec("component", part)],
                )
            )
    against = []
    others = [lot for lot in ordered if lot not in named and counts.get(lot["id"], 0)]
    if others:
        n = sum(counts[lot["id"]] for lot in others)
        against.append(
            _fact(
                f"{_n(n, 'complaint')} came from other lots ({_lot_list(others)}).",
                [_rec("lot", lot) for lot in others],
            )
        )
    missing = []
    no_lot = [c for c in complaints if c["lot_id"] is None]
    if no_lot:
        missing.append(_fact(f"Lot unknown on {_n(len(no_lot), 'complaint')}.", [_rec("complaint", c) for c in no_lot]))
    if unknown:
        missing.append(_fact(f"Units unknown for {_n(len(unknown), 'lot')}.", [_rec("lot", lot) for lot in unknown]))
    return [
        _draft(
            facts,
            "H-2",
            "H-2:" + ",".join(lot["id"] for lot in named),
            f"Lot or manufacturing: {_lot_list(named)}",
            f"Something in how {_lot_list(named)} were made or handled may explain the complaints, which concentrate there.",
            for_,
            against,
            missing,
            [lot["ref"] for lot in named],
        )
    ]


def h3_design(facts: dict) -> list[dict]:
    """H-3: a scope version's rate is higher than its predecessor's, spread across its lots (not concentrated)."""
    drafts = []
    as_of = facts["as_of"].date()
    problem = _all_problem_complaints(facts)
    for version in sorted((v for v in facts["versions"].values() if v["in_scope"]), key=lambda v: v["ref"]):
        prior = facts["versions"].get(version["predecessor_id"] or "")
        if prior is None or version["released"] is None:
            continue
        mine = [c for c in problem if c["version_id"] == version["id"]]
        theirs = [c for c in problem if c["version_id"] == prior["id"]]
        lots, prior_lots = _versions_lots(facts, [version["id"]]), _versions_lots(facts, [prior["id"]])
        days, prior_days = (as_of - version["released"]).days + 1, (as_of - prior["released"]).days + 1
        exposure = _exposure(lots, version["released"], as_of)
        prior_exposure = _exposure(prior_lots, prior["released"], as_of)
        if exposure and prior_exposure:
            mine_rate, prior_rate = len(mine) / exposure, len(theirs) / prior_exposure
        else:
            mine_rate, prior_rate = len(mine) / days, len(theirs) / prior_days
        counts = Counter(c["lot_id"] for c in mine if c["lot_id"])
        spread = len(counts) >= 2 and max(counts.values()) < LOT_COMPLAINT_SHARE * sum(counts.values())
        if not mine or mine_rate <= prior_rate or not spread:
            continue
        for_ = [
            _fact(
                f"{version['ref']}: {_rate_text(len(mine), exposure, days)} since its release; {prior['ref']}: "
                f"{_rate_text(len(theirs), prior_exposure, prior_days)} since its release.",
                [_rec("version", version), _rec("version", prior)] + [_rec("complaint", c) for c in mine],
            ),
            _fact(
                f"The complaints on {version['ref']} spread over {_n(len(counts), 'lot')}.",
                [_rec("lot", facts["lots"][lot_id]) for lot_id in sorted(counts) if lot_id in facts["lots"]],
            ),
        ]
        missing = []
        if not prior_exposure:
            missing.append(
                _fact(
                    f"{prior['ref']} has no units in the field recorded: compared by calendar days.",
                    [_rec("version", prior)],
                )
            )
        no_version = [c for c in facts["complaints"] if c["version_id"] is None]
        if no_version:
            missing.append(
                _fact(
                    f"Version unknown on {_n(len(no_version), 'complaint')}.",
                    [_rec("complaint", c) for c in no_version],
                )
            )
        drafts.append(
            _draft(
                facts,
                "H-3",
                f"H-3:{version['id']}",
                f"Design of {version['ref']}",
                f"Something in the design of {version['ref']}, compared with {prior['ref']}, may explain the complaints.",
                for_,
                [],
                missing,
                [f"design of {version['ref']}"],
            )
        )
    return drafts


def h4_use(facts: dict) -> list[dict]:
    """H-4: at least a third of scope complaints coded No Fault Found or user error, or a country cluster rather than
    a lot cluster."""
    complaints = facts["complaints"]
    coded = [c for c in complaints if c["code_class"]]
    countries = Counter(c["country"] for c in complaints if c["country"])
    top_country, held = countries.most_common(1)[0] if countries else (None, 0)
    lot_cluster = bool(h2_lots(facts))
    by_country = (
        bool(top_country) and held >= COUNTRY_SHARE * len(complaints) and len(countries) >= 1 and not lot_cluster
    )
    if not complaints or (len(coded) < USE_CODE_SHARE * len(complaints) and not by_country):
        return []
    for_ = []
    if coded:
        for_.append(
            _fact(
                f"{_n(len(coded), 'complaint')} coded No Fault Found or user error.",
                [_rec("complaint", c) for c in coded],
            )
        )
    if by_country:
        cited = [c for c in complaints if c["country"] == top_country]
        for_.append(
            _fact(
                f"{held} of {len(complaints)} complaints come from {top_country}.",
                [_rec("complaint", c) for c in cited],
            )
        )
    against = []
    if lot_cluster:
        against.append(
            _fact(
                "The complaints concentrate by lot (rule H-2), which points to how the devices were made rather than how they are used."
            )
        )
    faults = [c for c in complaints if c["returned"] and not c["code_class"] and c["service_status"] == "COMPLETE"]
    if faults:
        against.append(
            _fact(
                f"{_n(len(faults), 'returned device')} serviced without a No Fault Found code.",
                [_rec("complaint", c) for c in faults],
            )
        )
    missing = []
    not_returned = [c for c in complaints if not c["returned"]]
    if not_returned:
        missing.append(
            _fact(
                f"Device not returned (or not recorded) on {_n(len(not_returned), 'complaint')}.",
                [_rec("complaint", c) for c in not_returned],
            )
        )
    no_service = [c for c in complaints if c["service_status"] != "COMPLETE"]
    if no_service:
        missing.append(
            _fact(
                f"No service result on {_n(len(no_service), 'complaint')}.", [_rec("complaint", c) for c in no_service]
            )
        )
    return [
        _draft(
            facts,
            "H-4",
            "H-4",
            "Use, setting or environment",
            "How or where the device is used (settings, users, environment) may explain the complaints rather than the device.",
            for_,
            against,
            missing,
            USE_TERMS,
        )
    ]


def h5_supplier_part(facts: dict) -> list[dict]:
    """H-5: W1 rule P-1 finds the same problem on 2 or more versions sharing a part of one supplier."""
    box = facts.get("pattern")
    if not box or not box.get("found"):
        return []
    rows = box["versions"]
    for_ = [
        _fact(
            f"{row['product']} {row['version']}: {_n(row['recent'], 'complaint')} in {box['window_days']} days"
            + (f", {row['per_1000']} per 1,000 units" if row.get("per_1000") is not None else "")
            + ".",
            [{"type": "version", "id": row["version_id"], "ref": f"{row['product']} {row['version']}"}],
        )
        for row in rows
    ]
    shown = {row["version_id"] for row in rows}
    quiet = [v for v in box.get("part_versions", []) if v["id"] not in shown]
    against = (
        [
            _fact(
                f"{_n(len(quiet), 'version')} with {box['supplier']} parts show none of these complaints.",
                [{"type": "version", "id": v["id"], "ref": f"{v['product']} {v['ref']}"} for v in quiet],
            )
        ]
        if quiet
        else []
    )
    unknown = [row for row in rows if row.get("units_unknown_lots")]
    missing = [
        _fact(f"Units unknown for {_n(row['units_unknown_lots'], 'lot')} of {row['product']} {row['version']}.")
        for row in unknown
    ]
    return [
        _draft(
            facts,
            "H-5",
            f"H-5:{box['supplier_id']}",
            f"Supplier part across products: {box['supplier']}",
            f"A part from {box['supplier']}, shared by {_n(len(rows), 'version')}, may explain the same problem on each.",
            for_,
            against,
            missing,
            [box["supplier"]],
        )
    ]


def h0_not_enough(facts: dict) -> dict | None:
    """H-0: no rule can be tested (fewer than 3 scope complaints, or every complaint lacks version and lot)."""
    complaints = facts["complaints"]
    blind = all(c["version_id"] is None and c["lot_id"] is None for c in complaints)
    if len(complaints) >= MIN_COMPLAINTS and not blind:
        return None
    missing = [_fact(f"The scope holds {_n(len(complaints), 'complaint')}; the rules need at least {MIN_COMPLAINTS}.")]
    no_version = [c for c in complaints if c["version_id"] is None]
    no_lot = [c for c in complaints if c["lot_id"] is None]
    if no_version:
        missing.append(
            _fact(f"Version unknown on {_n(len(no_version), 'complaint')}.", [_rec("complaint", c) for c in no_version])
        )
    if no_lot:
        missing.append(_fact(f"Lot unknown on {_n(len(no_lot), 'complaint')}.", [_rec("complaint", c) for c in no_lot]))
    return _draft(
        facts,
        "H-0",
        "H-0",
        "Not enough records",
        "The records linked to this investigation are not enough to test any rule. Add what is missing, or request it.",
        [],
        [],
        missing,
        [],
    ) | {"duplicate_of": None}


def drafts(facts: dict) -> list[dict]:
    """Every draft whose condition is met, in rule order (never ranked). H-0 alone when no rule can be tested."""
    blocked = h0_not_enough(facts)
    if blocked is not None:
        return [blocked]
    return [*h1_changes(facts), *h2_lots(facts), *h3_design(facts), *h4_use(facts), *h5_supplier_part(facts)]
