"""Trial release 0.10.83, round D2 "Decide and report", the server half of each item.

D2.1-D2.3, the tree is the questionnaire: "serious injury" is a judgement, never pre-filled, with the record's words
beside it; questions earlier answers make unnecessary fold away with why, and are not required to sign; the Decision
trees tab lists the complaints still to assess, not only those already walked.
"""

from __future__ import annotations

import pytest

from backend.app.reportability import markets
from tests.test_market_assessment_api import (
    _acknowledge,
    _answers,
    _market,
    _save,
    _sign,
    _url,
    org,  # noqa: F401 (the module's organization fixture)
)
from tests.test_reporting_capa_api import PASSWORD, _complaint

RV11 = {"death": False, "serious_injury": False, "malfunction": True, "patient_involved": True, "severity": "No harm"}


def _a(**values: str) -> dict:
    return {key: {"answer": value, "rationale": "", "evidence": []} for key, value in values.items()}


# --------------------------------------------------------------------------------------------- D2.1-D2.3 (unit)


@pytest.mark.unit
def test_serious_injury_is_a_judgement_never_prefilled_with_the_records_words_beside_it():
    offered = markets.suggestions(markets.US_SET, RV11)
    assert sorted(offered) == ["US1", "US4"]
    assert not {"IN2B", "IN2D", "IN2F"} & set(markets.suggestions(markets.IN_SET, RV11))
    notes = markets.record_notes(markets.US_SET, RV11)
    assert sorted(notes) == ["US2A", "US2B", "US2C"]
    assert notes["US2A"] == ("The record says no serious injury was reported · severity “No harm”.")
    assert set(markets.record_notes(markets.IN_SET, RV11)) == {"IN2B", "IN2D", "IN2F"}
    for question in ("US2A", "US2B", "US2C", "IN2B", "IN2D", "IN2F"):
        assert question in markets.JUDGEMENT_QUESTIONS


@pytest.mark.unit
def test_questions_earlier_answers_make_unnecessary_fold_away_with_why():
    assert markets.not_asked(markets.US, {}) == {}
    no_harm = _a(US1="NO", US2A="NO", US2B="NO", US2C="NO")
    assert markets.not_asked(markets.US, no_harm) == {"US3": "Not asked: no death and no serious injury"}
    nothing = _a(US1="NO", US2A="NO", US2B="NO", US2C="NOT_APPLICABLE", US4="NO")
    assert markets.not_asked(markets.US, nothing) == {
        "US3": "Not asked: no death and no serious injury",
        "US5": "Not asked: no malfunction",
        "US6": "Not needed: not reportable on the answers above",
    }
    # Unknown never folds a question away: it is never No.
    assert markets.not_asked(markets.US, _a(US1="UNKNOWN", US2A="NO", US2B="NO", US2C="NO")) == {}
    assert set(markets.not_asked(markets.EU_NI, _a(EU1="NO"))) == {
        "EU2",
        *(f"EU3{letter}" for letter in "ABCDEF"),
        "EU4",
        "EU5",
        "EU6",
    }
    assert markets.not_asked(markets.CA, _a(CA1="YES", CA2="YES", CA3="YES", CA5="YES")) == {
        "CA4": "Not needed: it already led to death or a serious deterioration",
        "CA6": "Not asked: the incident occurred in Canada",
    }
    assert markets.evaluate(markets.US, no_harm)["not_asked"] == {"US3": "Not asked: no death and no serious injury"}


@pytest.mark.unit
def test_a_folded_question_is_not_required_to_sign():
    answers = {
        key: {"answer": value, "rationale": "Read from the record and the reporter's call", "evidence": []}
        for key, value in dict(US1="NO", US2A="NO", US2B="NO", US2C="NO", US4="NO").items()
    }
    assert markets.answers_problem(markets.US_SET, answers, complete=True) is None
    del answers["US4"]
    assert markets.answers_problem(markets.US_SET, answers, complete=True).startswith("Answer question US4")


# --------------------------------------------------------------------------------------------- D2.1-D2.3 (API)


@pytest.mark.db
def test_the_tree_lists_complaints_still_to_assess_and_signs_without_folded_questions(org):  # noqa: F811
    regulatory = org["regulatory"]
    complaint = _complaint(
        org["tenant_id"],
        org["product"],
        country="US",
        patient_involved=True,
        serious_injury=False,
        death=False,
        malfunction=True,
        severity="No harm",
    )
    trees = regulatory.get("/api/v1/decision-trees").json()
    listed = next(item for item in trees["complaints"] if item["id"] == complaint)
    assert listed["markets"] == [] and listed["signed"] == []

    detail = regulatory.get(_url(complaint)).json()
    us = _market(detail, "US")
    assert sorted(us["suggestions"]) == ["US1", "US4"]
    assert us["record_notes"]["US2B"].startswith("The record says no serious injury was reported")

    _acknowledge(regulatory, "US")
    # A malfunction with no harm that would not harm if it recurred: questions 3 and 6 fold away.
    item = _save(
        regulatory,
        complaint,
        "US",
        _answers(US1="NO", US2A="NO", US2B="NO", US2C="NO", US4="YES", US5="NO"),
        harm_level="NEGLIGIBLE",
    )
    assert item["evaluation"]["suggested"] == "NOT_REPORTABLE"
    assert item["evaluation"]["not_asked"] == {
        "US3": "Not asked: no death and no serious injury",
        "US6": "Not needed: not reportable on the answers above",
    }
    signed = _sign(regulatory, complaint, "US", item, "NOT_REPORTABLE", password=PASSWORD)
    assert signed.status_code == 200, signed.text
    path = regulatory.get(f"/api/v1/decision-trees?complaint_id={complaint}").json()["paths"]["US"]
    assert {node["id"]: node["not_asked"] for node in path["nodes"] if node["not_asked"]} == {
        "US3": "Not asked: no death and no serious injury",
        "US6": "Not needed: not reportable on the answers above",
    }


# --------------------------------------------------------------------------------------------- D2.5


@pytest.mark.db
def test_each_markets_tree_names_its_form_and_where_foreign_reporting_may_also_apply(org):  # noqa: F811
    trees = {tree["market"]: tree for tree in org["regulatory"].get("/api/v1/decision-trees").json()["markets"]}
    assert {market: tree["form"]["title"] for market, tree in trees.items()} == {
        "US": "Form FDA 3500A worksheet (eMDR)",
        "EU_NI": "EU Manufacturer Incident Report (MIR) worksheet",
        "GB": "Great Britain Manufacturer Incident Report (MHRA, GB MIR) worksheet",
        "IN": "MvPI Medical Device Adverse Event Reporting Form worksheet",
        "CA": "Health Canada mandatory medical device problem report worksheet",
    }
    assert trees["US"]["foreign"].startswith("FDA reporting can cover events outside the US")
    assert all(tree["foreign"] for tree in trees.values())


# --------------------------------------------------------------------------------------------- D2.7


@pytest.mark.unit
def test_each_report_field_says_who_knows_it_and_whether_it_is_entered_once():
    from backend.app.authority_reports import worksheet

    assert worksheet.scope_of("us_product_code") == worksheet.PRODUCT and worksheet.once_of("us_product_code")
    assert worksheet.scope_of("us_manufacturer") == worksheet.ORGANIZATION and worksheet.once_of("us_manufacturer")
    assert worksheet.scope_of("lot") == worksheet.EVENT and not worksheet.once_of("lot")
    # A brand name comes from the product's own name: the product's, but never typed here.
    assert worksheet.scope_of("brand_name") == worksheet.PRODUCT and not worksheet.once_of("brand_name")


@pytest.mark.db
def test_a_products_fact_is_entered_once_and_reused_on_every_report_of_that_product():
    from tests.test_free_trial import _approved_trial_client
    from tests.test_release_c3_0_10_75 import REPORTS, _flagship, _purge, _reports, _sign_us
    import uuid as _uuid

    user, approval, _ = _approved_trial_client()
    try:
        complaint = _flagship(user)
        assert _sign_us(user, complaint, "REPORTABLE").status_code == 200
        (report,) = _reports(user, complaint)
        detail = user.get(f"{REPORTS}/{report['id']}").json()
        fields = {item["id"]: item for section in detail["sections"] for item in section["fields"]}
        assert {item["scope"] for item in fields.values()} == {"PRODUCT", "ORGANIZATION", "EVENT"}
        once = [fields[key] for key in detail["mandatory"]["missing"] if fields[key]["once"]]
        assert once, [(key, fields[key]["label"]) for key in detail["mandatory"]["missing"]]
        values = {item["id"]: "Sample value 1" for item in once if item["once_key"] != "US_REGISTRATION"}
        pair = [item["id"] for item in once if item["once_key"] == "US_REGISTRATION"]
        refused = user.put(f"{REPORTS}/{report['id']}/once", json={"values": {"B5": "x"}})
        assert refused.status_code == 422 and refused.json()["detail"]["code"] == "NOT_ENTERED_ONCE"
        if pair:
            half = user.put(f"{REPORTS}/{report['id']}/once", json={"values": {pair[0]: "DQA"}})
            assert half.status_code == 422, half.text
        saved = user.put(f"{REPORTS}/{report['id']}/once", json={"values": values})
        assert saved.status_code == 200, saved.text
        after = {item["id"]: item for section in saved.json()["sections"] for item in section["fields"]}
        for field_id in values:
            assert after[field_id]["value"] and after[field_id]["status"] == "FROM_RECORD", after[field_id]
        # Never overwritten from a report: the product holds it now.
        again = user.put(f"{REPORTS}/{report['id']}/once", json={"values": values})
        assert again.status_code in (409, 422), again.text
    finally:
        _purge(_uuid.UUID(approval["tenant_id"]))


# --------------------------------------------------------------------------------------------- D2.8


@pytest.mark.db
def test_approval_in_plain_words_with_every_signatures_name_time_and_meaning():
    import uuid as _uuid

    from fastapi.testclient import TestClient

    from backend.app.main import app
    from tests.report_fill import fill
    from tests.test_free_trial import PASSWORD as TRIAL_PASSWORD
    from tests.test_free_trial import _activation_token, _approved_trial_client
    from tests.test_release_c3_0_10_75 import REPORTS, _flagship, _purge, _reports, _sign_us

    owner, approval, _ = _approved_trial_client()
    tenant_id = _uuid.UUID(approval["tenant_id"])
    try:
        mail = f"d2-{_uuid.uuid4().hex[:8]}@example.invalid"
        invited = owner.post(
            "/api/v1/trial/team", json={"email": mail, "display_name": "Rahul Iyer", "persona": "regulatory"}
        ).json()
        colleague = TestClient(app)
        token = _activation_token(invited, mail)
        assert (
            colleague.post(
                "/api/v1/auth/activate-account", json={"token": token, "password": TRIAL_PASSWORD}
            ).status_code
            == 200
        )
        assert (
            colleague.post("/api/v1/auth/signin", json={"email": mail, "password": TRIAL_PASSWORD}).status_code == 200
        )
        complaint = _flagship(owner)
        assert _sign_us(owner, complaint, "REPORTABLE").status_code == 200
        (report,) = _reports(owner, complaint)
        fill(owner, REPORTS, report["id"], owner.get(f"{REPORTS}/{report['id']}").json()["mandatory"]["missing"])
        sent = owner.post(f"{REPORTS}/{report['id']}/snapshots").json()
        # The approver reads the values as frozen, in the form's order.
        theirs = colleague.get(f"{REPORTS}/{report['id']}").json()
        frozen = theirs["pending_snapshot"]["sections"]
        assert [section["code"] for section in frozen] == [section["code"] for section in theirs["sections"]]
        # One task per approver, in plain words: no "snapshot", the customer's reference, who prepared it.
        tasks = colleague.get("/api/v1/tasks").json()["items"]
        titles = [task["title"] for task in tasks if task["title"].startswith("Approve")]
        assert titles == ["Approve the United States report for SAMPLE-RV-11 (prepared by Taylor Quality)"], titles
        assert [item["meaning"] for item in sent["signatures"]] == ["signed reportable", "prepared"]
        done = colleague.post(
            f"{REPORTS}/{report['id']}/snapshots/{theirs['pending_snapshot']['id']}/approve",
            json={"password": TRIAL_PASSWORD},
        )
        assert done.status_code == 200, done.text
        signatures = done.json()["signatures"]
        assert [(item["name"], item["meaning"]) for item in signatures][-1] == ("Rahul Iyer", "approved for submission")
        assert all(item["at"] for item in signatures)
        # The PDF prints each signature: name, moment and meaning (21 CFR 11.50); no "snapshot" in the meaning.
        from backend.app.authority_reports import render

        view = {
            **done.json(),
            "snapshot": done.json()["approved_snapshot"],
            "signature": {
                "signer_name": "Rahul Iyer",
                "signer_role": "Regulatory Leader",
                "signed_at": signatures[-1]["at"],
                "meaning": "I approve version 1 of the Form FDA 3500A (eMDR) for SAMPLE-RV-11 as the content to submit.",
                "record_business_id": "SIG-1",
                "record_id": "x",
                "content_fingerprint": "f" * 64,
            },
        }
        printed = render.manifestation(view)
        assert printed[0].startswith("Taylor Quality · ") and printed[0].endswith("· meaning: signed reportable")
        assert printed[2].startswith("Approved by Rahul Iyer (Regulatory Leader) · ")
        assert printed[2].endswith("meaning: approved for submission")
        # Records: the newest signature with its moment and meaning.
        latest = colleague.get("/api/v1/oversight/latest-signed").json()["record"]
        assert latest["meaning_label"] == "approved for submission" and latest["signed_at_time"]
        assert "snapshot" not in latest["meaning"]
    finally:
        _purge(tenant_id)
