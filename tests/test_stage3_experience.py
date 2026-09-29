from types import SimpleNamespace

from backend.app.stage3_router import agent_catalog, assurance_summary, product_version_story, reports_catalog, signal_detail, story_view


def _ctx():
    return SimpleNamespace(tenant_id="tenant-a", user_id="user-a")


def test_stage3_catalogs_are_governed_and_tenant_scoped():
    ctx = _ctx()
    reports = reports_catalog(ctx)
    agents = agent_catalog(ctx)
    assurance = assurance_summary(ctx)
    assert reports["tenant_id"] == "tenant-a"
    assert len(reports["reports"]) >= 10
    assert agents["human_authority_required"] is True
    assert all("DECLARE_ROOT_CAUSE" in item["forbidden"] for item in agents["agents"])
    assert assurance["guardrails"]["tenant_scope"] == "ENFORCED"


def test_story_not_found_is_non_disclosing():
    class EmptyDB:
        def execute(self, *args, **kwargs):
            return self

        def first(self):
            return None

    result = story_view("foreign-investigation", EmptyDB(), _ctx())
    assert result["status"] == "NOT_FOUND"
    assert "tenant-a" == result["tenant_id"]
    assert "foreign" not in result["message"].lower()


def test_signal_detail_is_tenant_scoped_and_non_disclosing_when_missing():
    class EmptyDB:
        def execute(self, *args, **kwargs):
            return self

        def rollback(self):
            pass

        def __iter__(self):
            return iter(())

    result = signal_detail("foreign-signal", EmptyDB(), _ctx())
    assert result["status"] == "NOT_FOUND"
    assert result["tenant_id"] == "tenant-a"
    assert "foreign" not in result["message"].lower()


def test_product_version_story_is_tenant_scoped_when_missing():
    class EmptyDB:
        def execute(self, *args, **kwargs):
            return self

        def rollback(self):
            pass

        def __iter__(self):
            return iter(())

    result = product_version_story("product-b", "version-b", EmptyDB(), _ctx())
    assert result["status"] == "NOT_FOUND"
    assert result["tenant_id"] == "tenant-a"
