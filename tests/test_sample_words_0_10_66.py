"""0.10.66 (stage 5, J18, V6): sample records name no codes, and a follow-up task's title is short. New trials are
seeded with today's wording; scripts/refresh_trial_story.py rewords a running trial's older records, once."""

from __future__ import annotations

import uuid

import pytest

from backend.app.db.models.guides_communications import CommunicationEntry
from backend.app.db.models.workflow import WorkflowTask
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_tenant
from backend.app.intake.service import FOLLOW_UP
from backend.app.trial.sample_guides import RV08_REQUEST, RV08_REQUEST_BEFORE
from backend.app.trial.sample_words import follow_up_title, reword_sample


@pytest.mark.unit
def test_an_old_follow_up_title_says_how_many_questions_are_open():
    old = "Follow up SAMPLE-CALL-03 with the reporter: ask about question 1, question 2, question 9"
    assert follow_up_title(old) == "Follow up SAMPLE-CALL-03 with the reporter: 3 open questions"
    assert follow_up_title("Follow up X with the reporter: ask about question 4") == (
        "Follow up X with the reporter: 1 open question"
    )
    assert follow_up_title("Follow up X with the reporter: ask whether any deficiency is alleged") == (
        "Follow up X with the reporter: is a deficiency alleged?"
    )
    assert follow_up_title("Follow up X with the reporter: 2 open questions") is None
    assert "US2A" not in RV08_REQUEST and "US2A" in RV08_REQUEST_BEFORE


@pytest.fixture(scope="module")
def trial():
    from backend.app.trial.retention import purge_trial
    from tests.test_free_trial import _approved_trial_client

    _user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    try:
        yield tenant_id
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:sample-words-cleanup")


@pytest.mark.db
def test_a_new_trial_has_todays_words_and_a_running_one_is_reworded_once(trial):
    db = SessionLocal()
    bind_tenant(db, trial)
    try:
        subjects = [row.subject for row in db.query(CommunicationEntry).filter(CommunicationEntry.tenant_id == trial)]
        assert RV08_REQUEST in subjects and not any("US2A" in subject for subject in subjects)
        tasks = (
            db.query(WorkflowTask).filter(WorkflowTask.tenant_id == trial, WorkflowTask.task_type == FOLLOW_UP).all()
        )
        assert tasks and not any("question 1," in task.title for task in tasks)
        assert reword_sample(db, trial, apply=False) == 0
        # A trial seeded before 0.10.66.
        entry = next(row for row in db.query(CommunicationEntry).filter(CommunicationEntry.subject == RV08_REQUEST))
        entry.subject = RV08_REQUEST_BEFORE
        tasks[0].title = "Follow up SAMPLE-CALL-03 with the reporter: ask about question 1, question 2"
        db.flush()
        assert reword_sample(db, trial, apply=False) == 2
        assert reword_sample(db, trial, apply=True) == 2
        db.flush()
        assert entry.subject == RV08_REQUEST
        assert tasks[0].title == "Follow up SAMPLE-CALL-03 with the reporter: 2 open questions"
        assert reword_sample(db, trial, apply=False) == 0
        db.commit()
    finally:
        db.close()
