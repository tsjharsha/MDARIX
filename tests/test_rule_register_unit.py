"""B4 step 1: the rule register's files, their checks and the version in force on a day (spec sections 4 and 5.1),
without a database. A fixture register in a temporary folder holds a test-only US-floor-2 and a correction."""

from __future__ import annotations

import copy
import json
from datetime import date, datetime, timezone

import pytest

from backend.app import standards
from backend.app.rule_register import register


def _write(folder, entries) -> None:
    for entry in entries:
        (folder / f"{entry['code']}.json").write_text(json.dumps(entry), encoding="utf-8")


def _version(base: dict, version: int, start, end, kind="LAW_CHANGE", corrects=None, **content) -> dict:
    entry = copy.deepcopy(base)
    entry.update(code=f"US-floor-{version}", version=version, effective_from=start, effective_to=end)
    entry["change"] = {"kind": kind, "reason": "test", **({"corrects": corrects} if corrects else {})}
    entry["content"].update(content)
    entry["content_hash"] = register.content_hash(entry["content"])
    return entry


@pytest.fixture
def use(tmp_path, monkeypatch):
    """Point the register at a fixture folder holding ``entries``; returns the loader's problems text on refusal."""

    def point(entries):
        folder = tmp_path / f"r{len(list(tmp_path.iterdir()))}"
        folder.mkdir()
        _write(folder, entries)
        monkeypatch.setattr(register, "_DIRECTORY", folder)
        return folder

    return point


@pytest.fixture
def us1():
    return copy.deepcopy(register._load(str(register.DATA))["US-floor-1"])


def test_the_real_register_loads_and_every_rule_carries_its_source_and_starter_mark():
    entries = register.load()
    floors = [entry for entry in entries.values() if entry["kind"] == "REPORTABILITY_FLOOR"]
    assert sorted(entry["code"] for entry in floors) == [
        "CA-floor-1",
        "CA-floor-2",
        "EU-floor-1",
        "EU-floor-2",  # G-10: question-6 skip wording (owner, 17 Nov 2026)
        "GB-floor-1",
        "GB-floor-2",  # G-10
        "IN-floor-1",
        "IN-floor-2",
        "OTHER-floor-1",  # B9b: a country outside the five markets
        "US-IMP-floor-1",
        "US-UF-floor-1",
        "US-floor-1",
    ]
    assert all(entry["review"]["note"] == standards.STARTER_MARK for entry in entries.values())
    assert all(source["catalog"] in standards.BY_ID for entry in entries.values() for source in entry["source"])
    # Stored codes are never renamed: the question sets keep theirs inside the floors.
    assert register.floor("US")["content"]["question_set"]["version"] == "US-starter-1"
    assert {"routine-basis-1", "disposition-starter-2", "provisional-starter-1", "emdr-rule-book-1"} <= set(entries)
    # Version 1 is in force from the start and open (R-D7).
    assert all(entry["effective_from"] is None and entry["effective_to"] is None for entry in entries.values())


def test_the_loader_refuses_an_unknown_catalog_id_a_duplicate_and_a_missing_field(use, us1):
    bad = copy.deepcopy(us1)
    bad["source"] = [{"catalog": "NOT_A_STANDARD", "clause": "x"}]
    use([bad])
    with pytest.raises(register.RegisterError, match=r"US-floor-1.json: unknown catalog id NOT_A_STANDARD"):
        register.load()
    twin = copy.deepcopy(us1)
    twin["rule"] = "other"
    folder = use([us1])
    (folder / "twin.json").write_text(json.dumps(twin), encoding="utf-8")
    with pytest.raises(register.RegisterError, match=r"code US-floor-1 also in twin.json"):
        register.load()
    lacking = {key: value for key, value in us1.items() if key != "approval"}
    use([lacking])
    with pytest.raises(register.RegisterError, match="missing approval"):
        register.load()


@pytest.mark.parametrize(
    ("built", "approver", "approver_name", "message"),
    [
        # Different typed names, one account: refused (owner decision O10, accounts, not names).
        ("sriharsha", "sriharsha", "Sriharsha", "an approver account other than"),
        ("srinivas", "srinivas", "Srinivas", "an approver account other than"),
        # An account that may not approve rule content.
        ("srinivas", "sriharsha", "Sriharsha", "an approver account other than"),
        # A typed name, an unknown account or none at all.
        ("sriharsha", "Srinivas", "Srinivas", "must be staff accounts"),
        ("sriharsha", "", "Srinivas", "must be staff accounts"),
        ("sriharsha", None, "Srinivas", "must be staff accounts"),
        # The right accounts, but a name that is not the approver account's.
        ("sriharsha", "srinivas", "Someone else", "must be the accounts' names"),
    ],
)
def test_a_version_approved_by_its_own_builder_or_by_nobody_is_refused(
    use, us1, built, approver, approver_name, message
):
    """B6b owner decisions O3 and O10 (MDX-VAL-002 RSK-065): builder and approver are two accounts, never one."""
    same = copy.deepcopy(us1)
    same["approval"].update(built_by_account=built, approved_by_account=approver, approved_by=approver_name)
    same["approval"]["built_by"] = register.STAFF_ACCOUNTS.get(built, ("Sriharsha",))[0]
    use([same])
    with pytest.raises(register.RegisterError, match=rf"US-floor-1.json: approval.*{message}"):
        register.load()


def test_a_version_approved_by_a_second_person_is_allowed(use, us1):
    other = copy.deepcopy(us1)
    other["approval"].update(
        built_by="Sriharsha",
        built_by_account="sriharsha",
        approved_by="Srinivas",
        approved_by_account="srinivas",
    )
    use([other])
    assert register.load()["US-floor-1"]["approval"]["approved_by_account"] == "srinivas"


def test_every_shipped_version_is_built_and_approved_by_two_accounts():
    """O10: the shipped register itself passes the account check."""
    for entry in register.load().values():
        assert entry["approval"]["built_by_account"] != entry["approval"]["approved_by_account"]


def test_content_changed_without_a_new_version_fails_naming_the_file(use, us1):
    """DT-33, RR-06: one byte of a floor's content changed, the hash left as it was."""
    changed = copy.deepcopy(us1)
    changed["content"]["report_types"]["US_30_DAY"]["days"] = 31
    use([changed])
    with pytest.raises(register.RegisterError, match=r"US-floor-1.json: content changed without a new version"):
        register.load()


def test_a_floor_whose_logic_names_an_unknown_question_is_refused(use, us1):
    broken = _version(us1, 1, None, None, kind="INITIAL", rules=[{"id": "F-US-9", "if": "US99", "cite": "x"}])
    use([broken])
    with pytest.raises(register.RegisterError, match="unknown question US99"):
        register.load()


@pytest.mark.parametrize(
    ("periods", "problem"),
    [
        ([(None, "2027-03-01"), ("2027-02-01", None)], "overlaps"),
        ([(None, "2027-03-01"), ("2027-04-01", None)], "gap from 2027-03-01 to 2027-04-01"),
        ([(None, "2027-03-01")], "gap after 2027-03-01"),
        ([("2027-03-01", "2027-02-01"), ("2027-02-01", None)], "is not after effective_from"),
    ],
)
def test_overlaps_gaps_and_an_end_before_a_start_are_refused(use, us1, periods, problem):
    """ED-12, RR-05."""
    use([_version(us1, index + 1, start, end) for index, (start, end) in enumerate(periods)])
    with pytest.raises(register.RegisterError, match=problem):
        register.load()


def test_a_floor_version_may_not_move_the_authority_zone(use, us1):
    """Review finding 3: floor_day dates events in today's version's zone, so a version naming another zone is refused."""
    moved = copy.deepcopy(us1["content"]["counting"])
    moved["authority_zone"] = "America/Chicago"
    use([_version(us1, 1, None, "2027-03-01", kind="INITIAL"), _version(us1, 2, "2027-03-01", None, counting=moved)])
    with pytest.raises(register.RegisterError, match="US-floor versions name different authority zones"):
        register.load()


def test_a_correction_must_keep_the_period_of_the_version_it_corrects(use, us1):
    v1 = _version(us1, 1, None, "2027-03-01", kind="INITIAL")
    v2 = _version(us1, 2, "2027-03-01", None)
    wrong = _version(us1, 3, None, None, kind="CORRECTION", corrects="US-floor-1")
    use([v1, v2, wrong])
    with pytest.raises(register.RegisterError, match="US-floor-3.json: a correction has the period of US-floor-1"):
        register.load()


def test_the_version_in_force_on_a_day_law_change_correction_and_scheduled(use, us1):
    """ED-13, RR-13: the highest version whose period contains the day; a future version is Scheduled."""
    v1 = _version(us1, 1, None, "2027-03-01", kind="INITIAL")
    v2 = _version(us1, 2, "2027-03-01", None)
    use([v1, v2])
    assert register.pick("US-floor", date(2027, 2, 28))["code"] == "US-floor-1"
    assert register.pick("US-floor", date(2027, 3, 1))["code"] == "US-floor-2"
    assert register.state(register.get("US-floor-2"), date(2026, 11, 11)) == "SCHEDULED"
    assert register.state(register.get("US-floor-1"), date(2027, 3, 2)) == "RETIRED"
    v3 = _version(us1, 3, None, "2027-03-01", kind="CORRECTION", corrects="US-floor-1")
    use([v1, v2, v3])
    assert register.pick("US-floor", date(2027, 2, 28))["code"] == "US-floor-3"
    assert register.state(register.get("US-floor-1"), date(2027, 2, 1)) == "REPLACED"
    assert register.pick("US-floor", date(2027, 3, 1))["code"] == "US-floor-2"


NY_EST = timezone(__import__("datetime").timedelta(hours=-5))


@pytest.mark.parametrize(
    ("aware", "expected"),
    [
        (datetime(2027, 2, 28, 23, 0, tzinfo=NY_EST), "US-floor-1"),  # ED-1
        (datetime(2027, 3, 1, 0, 0, tzinfo=NY_EST), "US-floor-2"),  # ED-2
        (datetime(2027, 3, 1, 3, 0, tzinfo=timezone.utc), "US-floor-1"),  # ED-3: 28 Feb in New York
        (date(2027, 3, 1), "US-floor-2"),  # ED-4: a date-only awareness
        (datetime(2027, 3, 1, 12, 0, tzinfo=timezone.utc), "US-floor-2"),  # a day-only moment (12:00 UTC) is that day
    ],
)
def test_the_awareness_day_in_the_authoritys_time_zone_picks_the_floor(use, us1, aware, expected):
    """ED-1..ED-4, RR-07 (R-D3): the authority's day picks the version, whatever the organization's zone."""
    use([_version(us1, 1, None, "2027-03-01", kind="INITIAL"), _version(us1, 2, "2027-03-01", None)])
    assert register.floor_at("US", aware, "Asia/Kolkata")["code"] == expected


def test_the_eu_floor_is_picked_on_the_brussels_day_across_summer_time(use):
    """ED-14: awareness 31 Mar 2027 22:30 UTC is 1 Apr 00:30 in Brussels (CEST, from 28 Mar): EU-floor-2 from 1 Apr."""
    eu1 = copy.deepcopy(register._load(str(register.DATA))["EU-floor-1"])

    def eu(version, start, end, kind):
        entry = copy.deepcopy(eu1)
        entry.update(code=f"EU-floor-{version}", version=version, effective_from=start, effective_to=end)
        entry["change"] = {"kind": kind, "reason": "test"}
        return entry

    use([eu(1, None, "2027-04-01", "INITIAL"), eu(2, "2027-04-01", None, "LAW_CHANGE")])
    assert register.floor_at("EU_NI", datetime(2027, 3, 31, 21, 30, tzinfo=timezone.utc))["code"] == "EU-floor-1"
    assert register.floor_at("EU_NI", datetime(2027, 3, 31, 22, 30, tzinfo=timezone.utc))["code"] == "EU-floor-2"
    assert register.floor_at("EU_NI", None)["code"] == "EU-floor-1"  # today (before 2027)


def _tier(aware) -> dict:
    from backend.app.intake import rules as intake

    found = intake.provisional_deadlines(aware, ["US", "EU_NI"], intake.FLAGGED, aware, own="US", org_zone="UTC")
    return {item["market"]: (item["days"], item["due_date"]) for item in found}


def test_triage_provisional_deadlines_follow_the_floor_at_awareness(use, us1):
    """ED-8, ED-10, ED-11, RR-08, RR-12: a law change after awareness does not move the provisional deadline; a
    correction that shortens a tier moves it at the next read; the EU never moves for a US change."""
    aware = datetime(2027, 2, 20, 12, tzinfo=timezone.utc)
    use([_version(us1, 1, None, None, kind="INITIAL")])
    before = _tier(aware)
    assert before["US"][0] == 30
    shorter = {**us1["content"]["provisional"], "FLAGGED": [20, "CALENDAR", "20 days (test only)"]}
    use(
        [
            _version(us1, 1, None, "2027-03-01", kind="INITIAL"),
            _version(us1, 2, "2027-03-01", None, provisional=shorter),
        ]
    )
    assert _tier(aware) == before  # ED-10: awareness before v2's day
    assert _tier(datetime(2027, 3, 2, 12, tzinfo=timezone.utc))["US"][0] == 20
    use(
        [
            _version(us1, 1, None, None, kind="INITIAL"),
            _version(us1, 3, None, None, kind="CORRECTION", corrects="US-floor-1", provisional=shorter),
            register._load(str(register.DATA))["EU-floor-1"],
        ]
    )
    after = _tier(aware)
    assert after["US"] == (20, "2027-03-12") and after["US"][1] < before["US"][1]  # ED-11
    assert after["EU_NI"] == before["EU_NI"]  # ED-8
    assert register.floor_at("EU_NI", aware)["code"] == "EU-floor-1"


def test_g10_version_2_says_a_risk_of_death_and_version_1_keeps_its_wording():
    # Owner approval 17 Nov 2026 (G-10): only question 6's skip note changes; signed conclusions keep version 1.
    new = "Not needed: death, or a risk of death, takes the 10-day report"
    old = "Not needed: a death takes the 10-day report"
    for market in ("GB", "EU"):
        entries = register.load()
        current = register.floor(market) or register.pick(f"{market}-floor")
        assert current["code"] == f"{market}-floor-2"
        assert new in str(current["content"]) and old not in str(current["content"])
        assert old in str(entries[f"{market}-floor-1"]["content"])
        assert current["change"] == {**current["change"], "kind": "CORRECTION", "corrects": f"{market}-floor-1"}
        assert current["approval"]["approved_by"] == "Srinivas" and current["approval"]["approved_on"] == "2026-11-17"
        v1, v2 = entries[f"{market}-floor-1"]["content"], current["content"]
        assert (
            v1["rules"] == v2["rules"]
            and v1["type_rows"] == v2["type_rows"]
            and v1["report_types"] == v2["report_types"]
        )
