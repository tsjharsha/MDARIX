"""E2: the validation evidence screen. The requirement and test mapping is read from the repository, a requirement
without a test shows as a gap, no recorded run says "No run recorded", and only an administrator, a free trial's owner
or a platform administrator reads it (a trial colleague is refused); only a platform administrator records a run."""

from __future__ import annotations

import io
import uuid
import zipfile

import pytest

from validation import docx_render, evidence_view

COMMIT = "a" * 40
JUNIT = f"""<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest" tests="3" timestamp="2026-11-17T10:00:00+00:00">
<properties><property name="commit" value="{COMMIT}"/><property name="tree" value="clean"/>
<property name="hook_version" value="2"/></properties>
<testcase classname="tests.test_market_assessment_rules" name="test_unknown_blocks_not_reportable" time="0.1">
<properties><property name="requirement" value="RG-05"/></properties></testcase>
<testcase classname="tests.test_market_assessment_api" name="test_each_market_signed" time="0.1">
<failure message="boom"/></testcase>
<testcase classname="tests.test_other" name="test_skipped" time="0"><skipped/></testcase>
</testsuite></testsuites>""".encode()


def _rows(view: dict) -> dict[str, dict]:
    return {row["req_id"]: row for row in view["requirements"]}


@pytest.mark.unit
def test_the_mapping_is_read_from_the_repository_requirements():
    sources = evidence_view.repo_sources()
    view = evidence_view.evidence(sources, None)
    rows = _rows(view)
    assert len(rows) == len(sources.requirements) == view["counts"]["requirements"] > 50
    first = rows["REQ-RPT-001"]
    assert [test["file"] for test in first["named_tests"]] == ["tests/test_market_assessment_rules.py"]
    assert first["class"] == "A" and "Unknown" in first["text"]


@pytest.mark.unit
def test_a_requirement_without_a_test_is_a_gap():
    view = evidence_view.evidence(evidence_view.repo_sources(), None)
    gap = _rows(view)["REQ-RPT-003"]  # requirements.csv names no test for it
    assert gap["gap"] is True and gap["result"] == "No test" and not gap["named_tests"]
    assert view["counts"]["gaps"] == sum(row["gap"] for row in view["requirements"]) >= 1
    assert view["counts"]["with_tests"] + view["counts"]["gaps"] == view["counts"]["requirements"]


@pytest.mark.unit
def test_without_a_recorded_run_every_result_says_no_run_recorded():
    view = evidence_view.evidence(evidence_view.repo_sources(), None)
    covered = [row for row in view["requirements"] if not row["gap"]]
    assert covered and {row["result"] for row in covered} == {"No run recorded"}
    assert {test["result"] for row in covered for test in row["named_tests"]} == {"No run recorded"}
    assert view["counts"]["passed"] == view["counts"]["failed"] == 0
    # The OQ protocol is not signed (owner decision): the screen says so, never "validated".
    assert view["protocol"]["signed"] is False


@pytest.mark.unit
def test_a_recorded_run_gives_each_requirement_its_last_result():
    run = evidence_view.parse_junit(JUNIT)
    assert run["commit"] == COMMIT and (run["passed"], run["failed"], run["skipped"]) == (1, 1, 1)
    assert run["ran_at"].isoformat() == "2026-11-17T10:00:00+00:00"
    rows = _rows(evidence_view.evidence(evidence_view.repo_sources(), run))
    passed, failed = rows["REQ-RPT-001"], rows["REQ-RPT-002"]
    assert passed["result"] == "Passed" and passed["named_tests"][0]["result"] == "Passed"
    assert passed["linked_tests"] == [
        {"id": "tests.test_market_assessment_rules::test_unknown_blocks_not_reportable", "result": "pass"}
    ]
    assert failed["result"] == "Failed"
    # A requirement whose named test file is not in this run is not passed by it.
    assert rows["REQ-RPT-004"]["result"] == "Not in this run"  # tests/test_b4_effective_dating.py did not run
    assert rows["REQ-RPT-003"]["result"] == "No test"


@pytest.mark.unit
@pytest.mark.parametrize(
    "raw",
    [
        b"<html><body>not a report</body></html>",
        b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><testsuites>&a;</testsuites>',
        b"<testsuites><testsuite/></testsuites>",
        b"not xml at all",
    ],
)
def test_anything_but_a_junit_report_is_refused(raw):
    with pytest.raises(ValueError):
        evidence_view.parse_junit(raw)


@pytest.mark.unit
def test_a_large_table_renders_without_the_per_cell_table_walk(monkeypatch):
    """table.cell(r, c) walks the whole table each call: the 180-row OQ protocol took a minute (E2 pack download)."""
    from docx.table import Table

    def walk(*_args, **_kwargs):
        raise AssertionError("table.cell is quadratic")

    monkeypatch.setattr(Table, "cell", walk)
    markdown = "# T\n\n| a | b |\n|---|---|\n" + "".join(f"| {i} | **x** |\n" for i in range(5))
    assert docx_render.render_docx(markdown, title="T", document_date="2026-11-17")[:2] == b"PK"


# ---- the API: who reads it, who records a run --------------------------------------------------------------------

READ = "/api/v1/admin/validation-evidence"
RECORD = "/api/v1/platform-admin/validation-runs"


@pytest.fixture(scope="module")
def trial():
    from backend.app.db.session import SessionLocal
    from backend.app.trial.retention import purge_trial
    from tests.test_free_trial import _approved_trial_client
    from tests.test_release_c1_0_10_73 import _invite

    owner, approval, _email = _approved_trial_client()
    _invited, colleague, _ = _invite(owner, "quality", "Second Reviewer")
    yield {"owner": owner, "colleague": colleague}
    with SessionLocal() as db:
        purge_trial(db, uuid.UUID(approval["tenant_id"]), "test:validation-evidence-cleanup")


def _upload(client, raw: bytes = JUNIT):
    return client.post(RECORD, files={"file": ("junit.xml", raw, "application/xml")})


@pytest.mark.db
def test_a_trial_colleague_is_refused_and_the_owner_and_platform_admin_read_it(trial):
    from tests.conftest import authenticated_client

    assert trial["colleague"].get(READ).status_code == 403
    assert trial["colleague"].get(f"{READ}/pack").status_code == 403
    shown = trial["owner"].get(READ)
    assert shown.status_code == 200, shown.text
    assert shown.json()["counts"]["gaps"] >= 1
    assert authenticated_client().get(READ).status_code == 200


@pytest.mark.db
def test_only_a_platform_admin_records_a_run_and_the_screen_shows_it(trial):
    from tests.conftest import authenticated_client

    assert _upload(trial["owner"]).status_code == 403
    refused = _upload(authenticated_client(), b"<html/>")
    assert refused.status_code == 422 and refused.json()["detail"]["code"] == "NOT_A_TEST_REPORT"
    recorded = _upload(authenticated_client())
    assert recorded.status_code == 201, recorded.text
    shown = trial["owner"].get(READ).json()
    assert shown["run"]["commit"] == COMMIT and shown["run"]["failed"] == 1
    assert _rows(shown)["REQ-RPT-002"]["result"] == "Failed"


@pytest.mark.db
def test_the_release_validation_pack_downloads_as_a_marked_dry_run(trial):
    answer = trial["owner"].get(f"{READ}/pack")
    assert answer.status_code == 200 and answer.headers["content-type"] == "application/zip"
    archive = zipfile.ZipFile(io.BytesIO(answer.content))
    names = archive.namelist()
    assert any(name.endswith("/MDX-VAL-009-RTM.pdf") for name in names)
    checks = archive.read(next(name for name in names if name.endswith("/checks.txt"))).decode()
    assert "is not signed" in checks


@pytest.mark.db
def test_the_run_table_migration_goes_down_and_up_again(migration_database):
    from sqlalchemy import text

    from tests.test_db1_migration_roundtrip import _alembic, _fingerprint

    engine, env = migration_database

    def present() -> bool:
        with engine.connect() as connection:
            return bool(connection.scalar(text("SELECT to_regclass('public.validation_test_runs') IS NOT NULL")))

    at_head = _fingerprint(engine)
    try:
        down = _alembic(env, "downgrade", "tr32aiready")
        assert down.returncode == 0, down.stderr[-2000:]
        assert not present()
    finally:
        up = _alembic(env, "upgrade", "head")
    assert up.returncode == 0, up.stderr[-2000:]
    assert present() and _fingerprint(engine) == at_head
