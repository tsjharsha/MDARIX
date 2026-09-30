from pathlib import Path


ROUTER = Path("backend/app/access_router.py").read_text(encoding="utf-8")


def test_customer_identity_provider_contract_is_tenant_scoped_and_redacted():
    assert '@router.get("/admin/security/identity-provider")' in ROUTER
    assert '@router.put("/admin/security/identity-provider")' in ROUTER
    assert "_admin_tenant(request, db)" in ROUTER
    assert "verification_required" in ROUTER
    section = ROUTER[
        ROUTER.index('@router.get("/admin/security/identity-provider")') : ROUTER.index(
            '@router.get("/admin/notifications/preferences")'
        )
    ]
    assert '"status": row.status' in section
    assert "row.configuration" not in section


def test_notification_contracts_are_durable_and_tenant_scoped():
    assert '@router.get("/admin/notifications/preferences")' in ROUTER
    assert '@router.put("/admin/notifications/preferences")' in ROUTER
    assert '@router.post("/admin/notifications/recipients")' in ROUTER
    assert "ReminderPolicyRecipient" in ROUTER
    assert "CUSTOMER_NOTIFICATION_PREFERENCES_UPDATED" in ROUTER


def test_customer_lifecycle_exposes_request_only_actions():
    assert '@router.get("/admin/tenant/lifecycle")' in ROUTER
    assert '@router.post("/admin/tenant/lifecycle/renewal-request")' in ROUTER
    section = ROUTER[ROUTER.index('@router.get("/admin/tenant/lifecycle")') :]
    assert '"platform_controlled_actions"' in section
    assert '"SUSPEND", "REACTIVATE", "TERMINATE", "ARCHIVE"' in section
