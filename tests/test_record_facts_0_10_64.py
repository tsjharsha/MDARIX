"""0.10.64, quality plan stage 3 E, "small truths in the records" (J22, J32): a product's device category, a lot's
expiry date, the software version (A8) from the product version, a kit's second lot that is not a duplicate, the IVDR
citation read from the product's own words on the watch as in triage, and the sample's product facts (seeded, and
filled in for running trials by scripts/refresh_trial_story.py). The CAPA's QMS reference is in
tests/test_decision_followups.py."""

from __future__ import annotations

import uuid
from datetime import date
from types import SimpleNamespace

import pytest

from backend.app import product_facts
from backend.app.authority_reports import forms, worksheet
from backend.app.db.models.foundation import Complaint, LotBatch, Product
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system, bind_tenant
from backend.app.reportability import markets
from backend.app.trial import imports

# ------------------------------------------------------------------------------------------------------ units


def test_device_category_reads_codes_and_plain_words():
    read = product_facts.category_code
    assert read("Single use") == read("single-use") == read("SINGLE_USE") == read("Disposable") == "SINGLE_USE"
    assert read("Capital equipment") == read("reusable") == "REUSABLE"
    assert read("Implantable") == "IMPLANT" and read("SaMD") == "SOFTWARE" and read("In vitro diagnostic") == "IVD"
    assert read("Procedure pack") == "KIT"
    assert read("") is None and read("Sterile") is None


def _context(category=None, version="Rev B", lot=None, other_lots=None) -> dict:
    product = SimpleNamespace(
        id=uuid.uuid4(),
        product_identifier="P-1",
        name="Pump",
        gmdn_term=None,
        gmdn_code=None,
        udi_di=None,
        device_category=category,
    )
    complaint = SimpleNamespace(
        id=uuid.uuid4(),
        complaint_identifier="OWN-1",
        description="Own",
        event_timestamp=None,
        death=None,
        serious_injury=None,
        patient_involved=None,
        malfunction=None,
        serial_number=None,
        udi=None,
        device_returned=None,
        problem_code=None,
        other_lots=other_lots,
    )
    return {
        "complaint": complaint,
        "record": {"business_id": "C-1", "complaint_identifier": "OWN-1", "version": version},
        "seen": {},
        "product": product,
        "lot": lot,
        "current": None,
        "draft": None,
        "classification": None,
        "case": None,
        "capas": [],
        "triage": None,
        "registrations": [],
        "parties": [],
        "imdrf": [],
        "sample": False,
    }


def _values(form, context) -> dict:
    return {
        item["id"]: item["value"] for section in worksheet.build(form, context, {}, {}) for item in section["fields"]
    }


def test_the_worksheets_fill_the_software_version_expiry_and_category_from_the_records():
    """J32: A8 was always empty; the expiry dates (India A13, FDA D4) and the India device category had no source."""
    lot = SimpleNamespace(id=uuid.uuid4(), lot_identifier="L-1", expiry_date=date(2029, 6, 30))
    software = _values(forms.MVPI_MDAE, _context("SOFTWARE", version="Rev 7", lot=lot))
    assert software["A8"] == "Rev 7" and software["A13"] == "2029-06-30"
    assert software["CAT2"] == "Non-implantable device" and software["CAT4"] is None
    numbered = _values(forms.MVPI_MDAE, _context(None, version="v2.4.1"))
    assert numbered["A8"] == "v2.4.1" and numbered["CAT2"] is None
    # A hardware revision is not a software version.
    assert _values(forms.MVPI_MDAE, _context("REUSABLE", version="Rev B"))["A8"] is None
    assert _values(forms.MVPI_MDAE, _context("REUSABLE"))["CAT4"] == "Reusable"
    implant = _values(forms.MVPI_MDAE, _context("IMPLANT"))
    assert implant["CAT2"] == "Implantable device"
    assert _values(forms.MVPI_MDAE, _context("SINGLE_USE"))["CAT4"] == "Single use"
    us = _values(forms.FDA_3500A, _context("KIT", lot=lot, other_lots=["L-2"]))
    assert us["D4_EXPIRY"] == "2029-06-30" and us["D4_LOT"] == "L-1; L-2"


def _check(csv_text: str) -> imports._Report:
    report = imports._Report()
    rows = imports._parse("complaints", csv_text.encode(), report, reading=imports.FileReading(date_column="none"))
    imports._check_values("complaints", rows, report)
    return report


def test_a_kits_second_lot_is_not_a_duplicate():
    """J32: a kit's complaint lists each of its lots on a row of its own; the second read "Duplicate of row 2"."""
    head = "complaint_id,product_id,description,lot_id\n"
    kit = _check(head + "K-1,KIT-9,Pack torn,L-1\nK-1,KIT-9,Pack torn,L-2\n")
    assert kit.error_count == 0, kit.issues
    again = _check(head + "K-1,KIT-9,Pack torn,L-1\nK-1,KIT-9,Pack torn,L-1\n")
    assert [issue["message"] for issue in again.issues] == ["Duplicate of row 2."]
    no_lot = _check(head + "K-1,KIT-9,Pack torn,L-1\nK-1,KIT-9,Pack torn,\n")
    assert [issue["message"] for issue in no_lot.issues] == ["Duplicate of row 2."]


def test_an_ivd_is_read_from_the_products_own_words():
    """The watch read only the product name while triage read its name, family, GMDN term and description."""
    product = SimpleNamespace(
        name="GlucoCheck 5", product_family="In-vitro diagnostics", gmdn_term=None, description=""
    )
    assert markets.product_is_ivd(product) and not markets.product_is_ivd(None)
    assert not markets.product_is_ivd(SimpleNamespace(name="Pump", product_family="", gmdn_term="", description=""))


# ------------------------------------------------------------------------------------------------------ trial


@pytest.fixture(scope="module")
def trial():
    from backend.app.trial.retention import purge_trial
    from tests.test_free_trial import _approved_trial_client

    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    try:
        yield {"user": user, "tenant_id": tenant_id}
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:record-facts-cleanup")


def _session(tenant_id):
    db = SessionLocal()
    bind_tenant(db, tenant_id)
    return db


@pytest.mark.db
def test_the_sample_products_carry_their_category_and_lots_their_expiry(trial):
    from backend.app.trial.sample_data import SAMPLE_PRODUCT_FACTS, SAMPLE_SOURCE, seed_product_facts

    with _session(trial["tenant_id"]) as db:
        products = db.query(Product).filter(Product.tenant_id == trial["tenant_id"]).all()
        assert {row.product_identifier: row.device_category for row in products} == {
            code: facts["device_category"] for code, facts in SAMPLE_PRODUCT_FACTS.items()
        }
        lots = db.query(LotBatch).filter(LotBatch.tenant_id == trial["tenant_id"]).all()
        assert lots and all(lot.expiry_date for lot in lots if lot.source_system == SAMPLE_SOURCE)
        lot = next(row for row in lots if row.lot_identifier == "SAMPLE-ORBIT-300-LOT-001")
        assert (lot.expiry_date - lot.effective_timestamp.date()).days == 1826
        # A running trial (before 0.10.64): refresh_trial_story.py fills them in, once.
        for row in products:
            row.device_category = None
        lot.expiry_date = None
        db.flush()
        assert seed_product_facts(db, trial["tenant_id"]) == {"products": 3, "lots": 1}
        assert seed_product_facts(db, trial["tenant_id"]) == {"products": 0, "lots": 0}
        db.commit()


@pytest.mark.db
def test_the_india_sample_worksheet_reads_the_category_and_expiry(trial):
    reports = trial["user"].get("/api/v1/reports").json()["items"]
    item = next(row for row in reports if row["complaint_identifier"] == "SAMPLE-RV-10" and row["market"] == "IN")
    detail = trial["user"].get(f"/api/v1/reports/{item['id']}").json()
    fields = {row["id"]: row for section in detail["sections"] for row in section["fields"]}
    assert fields["CAT2"]["value"] == "Non-implantable device" and fields["CAT4"]["value"] == "Reusable"
    assert fields["A13"]["value"] and fields["A13"]["source"]["label"] == "The lot's expiry date"
    assert fields["A8"]["value"] is None  # "Rev A" is a hardware revision


@pytest.mark.db
def test_products_and_lots_files_bring_the_category_and_expiry(trial):
    user = trial["user"]

    def upload(entity, text):
        return user.post(
            f"/api/v1/trial/imports/{entity}",
            params={"date_column": "none"},
            content=text,
            headers={"Content-Type": "text/csv"},
        )

    tag = uuid.uuid4().hex[:6].upper()
    refused = upload("products", f"product_id,product_name,device_category\nRF-{tag},Glucose Strips,Sterile\n")
    assert refused.status_code == 422
    assert product_facts.CATEGORY_HINT in str(refused.json())
    made = upload(
        "products", f"product_id,product_name,version,device category\nRF-{tag},Glucose Strips,2.1,Single use\n"
    )
    assert made.status_code == 200, made.text
    lots = upload("lots", f"lot_id,product_id,version,expiry date\nRF-{tag}-L1,RF-{tag},2.1,2028-01-31\n")
    assert lots.status_code == 200, lots.text
    kit = upload(
        "complaints",
        "complaint_id,product_id,description,lot_id\n"
        f"RF-{tag}-C1,RF-{tag},Strip pack torn,RF-{tag}-L1\nRF-{tag}-C1,RF-{tag},Strip pack torn,RF-{tag}-L2\n",
    )
    assert kit.status_code == 200, kit.text
    with SessionLocal() as db:
        bind_system(db, "test: read the records")
        product = db.query(Product).filter(Product.product_identifier == f"RF-{tag}").one()
        assert product.device_category == "SINGLE_USE"
        lot = db.query(LotBatch).filter(LotBatch.lot_identifier == f"RF-{tag}-L1").one()
        assert lot.expiry_date == date(2028, 1, 31)
        complaint = db.query(Complaint).filter(Complaint.complaint_identifier == f"RF-{tag}-C1").one()
        assert complaint.lot_batch_id == lot.id and complaint.other_lots == [f"RF-{tag}-L2"]


@pytest.mark.db
def test_the_watch_cites_the_ivdr_for_an_ivd_family(trial):
    """Stage 2's IVDR citation read only the product name on the watch, while triage read the family, GMDN term and
    description too: VentraLink in an IVD family stayed "MDR" on the watch. RV-07 is made a serious injury here, so its
    EU window's clock runs on the watch."""
    tenant_id = trial["tenant_id"]

    def change(family, injury, category):
        with _session(tenant_id) as db:
            product = (
                db.query(Product)
                .filter(Product.tenant_id == tenant_id, Product.product_identifier == "SAMPLE-VENTRA-250")
                .one()
            )
            complaint = (
                db.query(Complaint)
                .filter(Complaint.tenant_id == tenant_id, Complaint.complaint_identifier == "SAMPLE-RV-07")
                .one()
            )
            before = (product.product_family, complaint.serious_injury, product.device_category)
            product.product_family, complaint.serious_injury = family, injury
            # The words are the fallback for a product without a category (the sample's have one).
            product.device_category = category
            db.commit()
            return before

    before = change("In-vitro diagnostics", True, None)
    try:
        watch = trial["user"].get("/api/v1/complaints/reportability", params={"show": "all", "page_size": 100})
        rv07 = next(item for item in watch.json()["items"] if item["complaint_identifier"] == "SAMPLE-RV-07")
        bases = {basis for clock in rv07["clocks"] for basis in clock["basis"]}
        assert "IVDR_82" in bases and "MDR_87" not in bases
    finally:
        change(*before)


# ------------------------------------------------------- the single-use field and its use period (owner to approve)


def _product(**fields):
    base = dict(name="Pump", product_family="", gmdn_term="", description="", device_category=None)
    base.update(single_use=None, use_period_days=None)
    return SimpleNamespace(**{**base, **fields})


def test_the_product_fields_decide_before_the_words():
    from backend.app.signals import trend_rules

    # The words remain the fallback for a product without a category or a single-use field.
    assert trend_rules.product_basis(_product(name="Sterile catheter")) == (True, None)
    # A category or the field overrides them: a "catheter" marked reusable is counted by units in the field.
    assert trend_rules.product_basis(_product(name="Sterile catheter", device_category="REUSABLE")) == (False, None)
    assert trend_rules.product_basis(_product(name="Sterile catheter", single_use=False)) == (False, None)
    assert trend_rules.product_basis(_product(device_category="KIT")) == (True, None)
    assert trend_rules.product_basis(_product(single_use=True, use_period_days=90)) == (True, 90)
    assert trend_rules.product_basis(_product(single_use=False, use_period_days=90)) == (False, None)
    # The IVDR: the category when set, else the words.
    assert markets.product_is_ivd(_product(device_category="IVD"))
    assert not markets.product_is_ivd(_product(name="Reagent analyser", device_category="REUSABLE"))
    assert markets.product_is_ivd(_product(name="Reagent analyser"))


def test_a_use_period_counts_each_lot_only_while_its_units_are_in_use():
    from backend.app.signals import trend_rules

    lots = [(date(2026, 1, 1), 100)]
    # 1 Jan to 30 Jan: 30 days in use in full without a period, 10 with a 10-day one.
    assert trend_rules.unit_days(lots, date(2026, 1, 1), date(2026, 1, 30)) == 3000
    assert trend_rules.unit_days(lots, date(2026, 1, 1), date(2026, 1, 30), use_days=10) == 1000
    # A lot whose period ended before the window adds nothing.
    assert trend_rules.unit_days(lots, date(2026, 3, 1), date(2026, 3, 30), use_days=10) is None


def test_h5_reads_the_single_use_field():
    assert _values(forms.FDA_3500A, _context())["H5"] is None
    context = _context()
    context["product"].single_use = True
    assert _values(forms.FDA_3500A, context)["H5"] == "Yes"


@pytest.mark.db
def test_the_products_file_brings_the_single_use_field_and_use_period(trial):
    user = trial["user"]
    tag = uuid.uuid4().hex[:6].upper()

    def upload(text):
        return user.post("/api/v1/trial/imports/products", content=text, headers={"Content-Type": "text/csv"})

    head = "product_id,product_name,single_use,use_period_days\n"
    assert upload(head + f"SU-{tag},Wound dressing,maybe,30\n").status_code == 422
    assert upload(head + f"SU-{tag},Wound dressing,Y,0\n").status_code == 422
    made = upload(head + f"SU-{tag},Wound dressing,Y,30\n")
    assert made.status_code == 200, made.text
    with SessionLocal() as db:
        bind_system(db, "test: read the product")
        product = db.query(Product).filter(Product.product_identifier == f"SU-{tag}").one()
        assert product.single_use is True and product.use_period_days == 30
    with _session(trial["tenant_id"]) as db:
        sample = db.query(Product).filter(Product.tenant_id == trial["tenant_id"]).all()
        assert {row.single_use for row in sample if row.source_system == "MDARIX_SAMPLE"} == {False}
