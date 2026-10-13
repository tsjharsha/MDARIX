"""The emails of ending a free trial early (auth/emailer.py, backend/app/trial/early_exit.py), without a database."""

from __future__ import annotations

import pytest

from auth import emailer
from backend.app.trial.early_exit import EXIT_REASONS


@pytest.fixture
def sent(monkeypatch):
    messages = []
    monkeypatch.setattr(
        emailer, "_send", lambda recipient, message, **_: messages.append((recipient, message)) or "SENT"
    )
    return messages


def test_the_owner_is_told_the_data_is_deleted_and_asked_why_by_reply(sent):
    assert emailer.send_trial_ended_early("owner@acme.invalid", "Acme", data_deleted=True) == "SENT"
    recipient, message = sent[0]
    assert recipient == "owner@acme.invalid"
    assert message.subject == "Your MDARIX trial has ended"
    text = " ".join(message.paragraphs)
    assert "has been deleted" in text and "without names or email addresses" in text
    assert "Simply reply to this email" in text
    assert message.details == ()


def test_the_owner_is_told_until_when_the_data_is_kept(sent):
    emailer.send_trial_ended_early("owner@acme.invalid", "Acme", data_deleted=False, delete_on="13 November 2026")
    message = sent[0][1]
    assert ("Data deleted on", "13 November 2026") in message.details
    assert "kept until the date below" in " ".join(message.paragraphs)
    plain, html = emailer.render(message)
    assert "13 November 2026" in plain and "13 November 2026" in html


def test_a_declined_request_carries_the_teams_note_and_the_platform_team_is_alerted(sent):
    emailer.send_trial_exit_declined("owner@acme.invalid", "Acme", note="Could we talk first?")
    assert "Could we talk first?" in sent[0][1].paragraphs
    emailer.send_trial_exit_request_alert(
        "trials@mdarix.invalid",
        organization="Acme",
        requested_by="Asha (owner@acme.invalid)",
        reason="Something we need is missing; QMS first",
        delete_data=True,
        days_left=21,
    )
    alert = sent[1][1]
    assert alert.subject == "Trial early end requested: Acme"
    assert ("Their data", "Delete it") in alert.details and ("Days left", "21") in alert.details
    assert ("Why", "Something we need is missing; QMS first") in alert.details


def test_the_reasons_offered_are_short_and_end_with_another_reason():
    assert list(EXIT_REASONS)[-1] == "OTHER"
    assert all(len(label) <= 40 for label in EXIT_REASONS.values())
