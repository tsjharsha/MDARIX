"""0.10.80: a trial with both the sample and its own imported complaints shows them separately ("Sample data · Your
data" on the new navigation's top bar). Automatic insights read the data the person chose (``?source=``); without a
choice they read as before: the imported data, else the sample.
"""

import inspect

from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_tenant
from backend.app.trial import imports, router
from backend.app.trial.sample_data import SAMPLE_SOURCE, seed_sample_workspace
from tests.test_trial_insights import (  # noqa: F401  (the fixture is used by name)
    NOW,
    _uploaded_workspace,
    workspaces,
)


def test_insights_read_the_chosen_data_and_default_as_before(workspaces):  # noqa: F811
    tenant_id = _uploaded_workspace(workspaces)
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        seed_sample_workspace(db, tenant_id, NOW)
        db.commit()
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        default = imports.insights(db, tenant_id)
        own = imports.insights(db, tenant_id, source=imports.UPLOAD_SOURCE)
        sample = imports.insights(db, tenant_id, source=SAMPLE_SOURCE)
        unknown = imports.insights(db, tenant_id, source="SOMETHING_ELSE")
    # Without a choice (or an unknown one): the imported data, as before 0.10.80.
    assert default["source_system"] == own["source_system"] == unknown["source_system"] == imports.UPLOAD_SOURCE
    assert default["scope"] == own["scope"] == "your data"
    assert default["total_complaints"] == own["total_complaints"] == 12
    # The sample, chosen beside the imported data.
    assert sample["source_system"] == SAMPLE_SOURCE and sample["scope"] == "sample data"
    assert sample["total_complaints"] > 0 and sample["total_complaints"] != own["total_complaints"]


def test_the_route_takes_the_choice_as_a_bounded_query_parameter():
    parameter = inspect.signature(router.trial_insights).parameters["source"]
    assert parameter.default.default == "" and parameter.default.metadata[0].max_length == 40
