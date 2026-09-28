from backend.app.audit_chain import audit_event_hash, verify_audit_chain


def test_audit_chain_detects_tampering():
    first = {"id": "1", "tenant_id": "a", "action": "CREATE", "entity_type": "X", "created_at": "2026-01-01"}
    first["previous_hash"] = None
    first["event_hash"] = audit_event_hash(first)
    second = {"id": "2", "tenant_id": "a", "action": "UPDATE", "entity_type": "X", "created_at": "2026-01-02"}
    second["previous_hash"] = first["event_hash"]
    second["event_hash"] = audit_event_hash(second, second["previous_hash"])
    assert verify_audit_chain([first, second])["valid"] is True
    second["action"] = "DELETE"
    assert verify_audit_chain([first, second])["valid"] is False
