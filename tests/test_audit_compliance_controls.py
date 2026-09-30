import gzip
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from backend.app.enterprise_audit import change_diff, make_audit_event
from backend.app.retention import archive_expired_audit_events


def test_audit_diff_is_redacted_and_contains_only_changed_values():
    old, new = change_diff({"status": "DRAFT", "token": "secret"}, {"status": "ACTIVE", "token": "changed"})
    assert old == {"status": "DRAFT"}
    assert new == {"status": "ACTIVE"}


def test_audit_event_captures_request_origin_and_retention():
    request = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"), headers={"user-agent": "pytest"})
    event = make_audit_event(
        tenant_id="tenant-a",
        actor_ref="user-a",
        action="UPDATE",
        entity_type="Test",
        request=request,
        old_values={"status": "DRAFT"},
        new_values={"status": "ACTIVE"},
    )
    assert event.source_ip == "127.0.0.1"
    assert event.user_agent == "pytest"
    assert event.old_values == {"status": "DRAFT"}
    assert event.new_values == {"status": "ACTIVE"}
    assert event.retention_until > event.created_at + timedelta(days=365 * 6)


def test_expired_audit_events_are_archived_without_deletion(tmp_path):
    now = datetime.now(timezone.utc)
    event = SimpleNamespace(
        id="e1",
        tenant_id="tenant-a",
        actor_ref="u1",
        action="UPDATE",
        entity_type="Test",
        entity_id=None,
        details={},
        source_ip="127.0.0.1",
        user_agent="pytest",
        reason="test",
        old_values={"a": 1},
        new_values={"a": 2},
        retention_until=now - timedelta(days=1),
        created_at=now - timedelta(days=2),
    )
    result = archive_expired_audit_events([event], archive_dir=tmp_path, now=now)
    assert result["status"] == "ARCHIVED"
    archive = next(tmp_path.glob("*.jsonl.gz"))
    with gzip.open(archive, "rt", encoding="utf-8") as stream:
        row = json.loads(stream.readline())
    assert row["tenant_id"] == "tenant-a"
    assert row["old_values"] == {"a": 1}
