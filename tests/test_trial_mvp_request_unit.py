"""The emails around an MVP conversation (auth/emailer.py), without a database: the MDARIX team's alert, and the line
the trial's last reminders carry to Next steps."""

from __future__ import annotations

import pytest

from auth import emailer


@pytest.fixture
def sent(monkeypatch):
    messages = []
    monkeypatch.setattr(
        emailer, "_send", lambda recipient, message, **_: messages.append((recipient, message)) or "SENT"
    )
    return messages


def test_the_team_hears_what_the_trial_expects_and_whether_to_move_its_data(sent):
    emailer.send_trial_mvp_request_alert(
        "support@mdarix.invalid",
        display_name="Priya Sharma",
        email="priya@orbit.invalid",
        organization="Orbit Medical Devices",
        expectations="Find hidden complaints across two pump lines.",
        scope="OrbitCare 300; TrackWise and SAP",
        phone="+91 98450 12345",
        contact_preference="Tuesday afternoon IST",
        move_trial_data=True,
        days_left=12,
    )
    recipient, message = sent[0]
    assert recipient == "support@mdarix.invalid"
    assert message.subject == "MVP conversation requested: Orbit Medical Devices"
    details = dict(message.details)
    assert details["Email"] == "priya@orbit.invalid" and details["Phone"] == "+91 98450 12345"
    assert details["Trial data"] == "Move it into the MVP" and details["Days left in the trial"] == "12"
    assert "Find hidden complaints across two pump lines." in " ".join(message.paragraphs)
    assert "OrbitCare 300; TrackWise and SAP" in " ".join(message.paragraphs)
    plain, html = emailer.render(message)
    assert "Priya Sharma" in plain and "Orbit Medical Devices" in html


def test_an_update_says_so_and_leaves_out_what_was_not_given(sent):
    emailer.send_trial_mvp_request_alert(
        "support@mdarix.invalid",
        display_name="Priya Sharma",
        email="priya@orbit.invalid",
        organization="Orbit <Devices>",
        expectations="Only the hidden complaints.",
        updated=True,
    )
    message = sent[0][1]
    assert message.subject == "MVP conversation request updated: Orbit <Devices>"
    labels = [label for label, _ in message.details]
    assert "Phone" not in labels and "How and when to reach them" not in labels
    assert dict(message.details)["Trial data"] == "Start the MVP without it"
    # What people typed is escaped in the HTML version.
    assert "Orbit &lt;Devices&gt;" in emailer.render(message)[1]


def test_the_last_reminders_point_to_next_steps(sent, monkeypatch):
    monkeypatch.setenv("MDARIX_APP_URL", "https://app.mdarix.invalid")
    emailer.send_trial_reminder(
        "owner@orbit.invalid", "Orbit", days_left=7, ends_on="30 October 2026", delete_on="29 November 2026"
    )
    text = " ".join(sent[0][1].paragraphs)
    assert "https://app.mdarix.invalid/app/next-steps" in text
    # No prices or discount figures in any of it.
    assert not any(symbol in text for symbol in ("$", "€", "₹", "%"))
