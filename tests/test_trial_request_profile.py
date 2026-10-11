"""The trial request profile on its own (backend/app/trial/request_profile.py): required answers, fixed choices, what the
review screen reads and what the purge keeps. The sign-up route itself is covered in tests/test_free_trial.py."""

from types import SimpleNamespace

import pytest

from backend.app.trial import request_profile as rp


def _signup(**answers):
    base = {
        "job_title": "Director of Quality",
        "country": "India",
        "phone": None,
        "company_size": None,
        "device_types": None,
        "device_class": None,
        "markets": [],
        "complaint_system": None,
        "complaint_volume": None,
        "trial_data": None,
        "evaluation_goal": None,
        "no_patient_data": True,
    }
    return SimpleNamespace(**{**base, **answers})


def test_the_three_required_answers_are_enforced():
    for answers, code in (
        ({"job_title": "  "}, "JOB_TITLE_REQUIRED"),
        ({"country": ""}, "COUNTRY_REQUIRED"),
        ({"no_patient_data": False}, "NO_PATIENT_DATA_CONFIRMATION_REQUIRED"),
    ):
        with pytest.raises(rp.ProfileError) as problem:
            rp.build_profile(_signup(**answers))
        assert problem.value.code == code


def test_only_offered_choices_are_stored_and_empty_answers_are_left_out():
    profile = rp.build_profile(
        _signup(
            job_title="  Head   of QA ",
            phone="+91 98400 80008",
            company_size="201-1000",
            device_class="CLASS_II",
            markets=["US", "EU", "US"],
            complaint_system="TRACKWISE",
            complaint_volume="50_500",
            trial_data="ANONYMIZED_EXPORTS",
            evaluation_goal="  Faster trending  ",
        )
    )
    assert profile == {
        "job_title": "Head of QA",
        "country": "India",
        "phone": "+91 98400 80008",
        "company_size": "201-1000",
        "device_class": "CLASS_II",
        "markets": ["US", "EU"],
        "complaint_system": "TRACKWISE",
        "complaint_volume": "50_500",
        "trial_data": "ANONYMIZED_EXPORTS",
        "evaluation_goal": "Faster trending",
        "no_patient_data_confirmed": True,
    }
    assert rp.build_profile(_signup()) == {
        "job_title": "Director of Quality",
        "country": "India",
        "no_patient_data_confirmed": True,
    }
    for answers, code in (
        ({"company_size": "huge"}, "INVALID_COMPANY_SIZE"),
        ({"device_class": "CLASS_IV"}, "INVALID_DEVICE_CLASS"),
        ({"markets": ["MARS"]}, "INVALID_MARKET"),
        ({"complaint_system": "PAPER"}, "INVALID_COMPLAINT_SYSTEM"),
        ({"complaint_volume": "LOTS"}, "INVALID_COMPLAINT_VOLUME"),
        ({"trial_data": "LIVE_PATIENT_DATA"}, "INVALID_TRIAL_DATA"),
        ({"phone": "call me maybe"}, "VALID_PHONE_REQUIRED"),
        ({"phone": "12345"}, "VALID_PHONE_REQUIRED"),
    ):
        with pytest.raises(rp.ProfileError) as problem:
            rp.build_profile(_signup(**answers))
        assert problem.value.code == code


def test_the_review_screen_reads_labels_not_codes():
    lines = dict(
        rp.describe(rp.build_profile(_signup(device_class="IVD", markets=["UK", "CA"], complaint_system="VEEVA_QMS")))
    )
    assert lines["Highest device class"] == "In vitro diagnostic (IVD)"
    assert lines["Markets"] == "United Kingdom, Canada"
    assert lines["Complaint system"] == "Veeva QMS"
    assert lines["No patient data"] == "Confirmed"
    assert rp.describe({}) == []


def test_the_purge_keeps_company_facts_and_drops_the_person():
    profile = rp.build_profile(
        _signup(phone="+1 555 010 0199", company_size="51-200", evaluation_goal="Ask Priya about CAPA trends")
    )
    kept = rp.erase_personal(profile)
    assert "job_title" not in kept and "phone" not in kept and "evaluation_goal" not in kept
    assert kept["company_size"] == "51-200" and kept["country"] == "India"
    assert rp.erase_personal(None) == {}
