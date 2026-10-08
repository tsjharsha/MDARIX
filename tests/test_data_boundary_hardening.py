"""Customer records stay out of error reports, database error messages, the worker's blind spot and the model path.

- The error reporter receives the shape of an error (type, frames, method and path), never messages, variables,
  breadcrumbs or request content, any of which can quote a record.
- A failing statement on a tenant's dedicated database does not repeat its bound values.
- The outbox worker binds the tenant on a dedicated database as it does on the shared one.
- Schema discovery reads the connector's schema page for the tenant, not its health page.
- A staging or production server never downloads the embedding model, and refuses to start with a missing or
  altered one.
"""

import importlib.util
import uuid
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

import retrieval.embedding_provider as embedding
from backend.app import logging_setup
from backend.app.access import common
from backend.app.db import data_plane
from backend.app.db.session import engine
from backend.app.db.tenant_scope import scope_of

PLANE_REF = "MDARIX_DATA_PLANE_BOUNDARY_TEST_DATABASE_URL"


@pytest.fixture
def test_plane(monkeypatch):
    """The test database, registered as if it were a tenant's dedicated database."""
    monkeypatch.setenv(PLANE_REF, engine.url.render_as_string(hide_password=False))
    data_plane.session_factory.cache_clear()
    yield "boundary-test"
    data_plane.session_factory.cache_clear()


def test_error_reports_keep_the_shape_of_an_error_and_nothing_a_record_could_be_read_from():
    event = {
        "request": {
            "url": "https://app.example/api/v1/complaints",
            "method": "POST",
            "data": {"description": "patient Jane"},
            "headers": {"Cookie": "session=Jane"},
            "query_string": "q=Jane",
            "cookies": {"s": "Jane"},
            "env": {"REMOTE_ADDR": "Jane"},
        },
        "user": {"id": "Jane"},
        "breadcrumbs": {"values": [{"message": "SELECT ... 'Jane'"}]},
        "extra": {"row": "Jane"},
        "logentry": {"message": "failed for %s", "params": ["Jane"]},
        "message": "failed for Jane",
        "exception": {
            "values": [
                {
                    "type": "DataError",
                    "value": "invalid input syntax: 'Jane'",
                    "stacktrace": {
                        "frames": [
                            {
                                "filename": "a.py",
                                "function": "f",
                                "lineno": 3,
                                "vars": {"description": "Jane"},
                                "context_line": "x = 'Jane'",
                                "pre_context": ["# Jane"],
                                "post_context": ["# Jane"],
                            }
                        ]
                    },
                }
            ]
        },
    }
    scrubbed = logging_setup._scrub_event(event, None)
    assert "Jane" not in repr(scrubbed)
    assert scrubbed["request"] == {"url": "https://app.example/api/v1/complaints", "method": "POST"}
    error = scrubbed["exception"]["values"][0]
    assert error["type"] == "DataError" and error["value"] == ""
    assert error["stacktrace"]["frames"] == [{"filename": "a.py", "function": "f", "lineno": 3}]


def test_a_failing_statement_on_a_tenant_database_does_not_repeat_its_values(test_plane):
    factory = data_plane.session_factory(test_plane, PLANE_REF)
    with factory() as db, pytest.raises(DBAPIError) as failure:
        db.execute(text("SELECT :value FROM table_that_does_not_exist"), {"value": "record-text-ZZSECRET"})
    assert "ZZSECRET" not in str(failure.value)
    assert "hidden" in str(failure.value)


def _worker():
    path = Path(__file__).resolve().parents[1] / "scripts" / "run_outbox_worker.py"
    spec = importlib.util.spec_from_file_location("run_outbox_worker_boundary", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_outbox_worker_binds_the_tenant_on_a_dedicated_database_too(test_plane):
    tenant_id = uuid.uuid4()
    plane = SimpleNamespace(tenant_id=tenant_id, database_ref=test_plane, connection_secret_ref=PLANE_REF)
    with _worker().plane_session(plane) as db:
        scope = scope_of(db)
    assert scope["tenant_id"] == str(tenant_id) and not scope["system_reason"]


def test_schema_discovery_reads_the_schema_page_of_the_tenant(monkeypatch):
    paths, opened = [], []

    def fake_safe_url(endpoint, path, timeout):
        paths.append(path)
        return f"{endpoint}/{path}"

    @contextmanager
    def fake_urlopen(request, timeout):
        opened.append(request.full_url)
        yield SimpleNamespace(status=200, read=lambda limit: b"{}")

    monkeypatch.setattr(common, "_safe_provider_url", fake_safe_url)
    monkeypatch.setattr(common, "_connector_credential", lambda configuration, row: None)
    monkeypatch.setattr(common, "safe_urlopen", fake_urlopen)
    row = SimpleNamespace(id=uuid.uuid4(), configuration={"endpoint": "https://source.example", "tenant_key": "ACME"})

    assert common._provider_get(row, "schema_path")["status"] == "HEALTHY"
    assert common._provider_get(row, "health_path")["status"] == "HEALTHY"
    assert paths == ["schema", "health"]
    assert opened == ["https://source.example/schema?tenant=ACME", "https://source.example/health?tenant=ACME"]


def test_a_production_server_never_downloads_the_embedding_model(monkeypatch, tmp_path):
    monkeypatch.setenv("MDARIX_ENV", "production")
    monkeypatch.setenv("MDARIX_EMBEDDING_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(embedding.LocalModelEmbeddingProvider, "_model", None)
    with pytest.raises(embedding.EmbeddingUnavailable, match="never downloads"):
        embedding.LocalModelEmbeddingProvider().embed_text("anything")
    assert not any(tmp_path.iterdir())


def test_the_configuration_check_requires_the_pinned_embedding_model(monkeypatch, tmp_path):
    from backend.app.config_check import _embedding_model_problem

    monkeypatch.setenv("MDARIX_EMBEDDING_CACHE_DIR", str(tmp_path))
    monkeypatch.delenv("MDARIX_EMBEDDING_PROVIDER", raising=False)
    assert "never downloads" in (_embedding_model_problem() or "")
    weights = tmp_path / "models--x" / "snapshots" / "rev" / "model_optimized.onnx"
    weights.parent.mkdir(parents=True)
    weights.write_bytes(b"swapped weights")
    assert "checksum differs" in (_embedding_model_problem() or "")
    monkeypatch.setenv("MDARIX_EMBEDDING_PROVIDER", "deterministic")
    assert _embedding_model_problem() is None


@pytest.mark.skipif(not embedding.DEFAULT_CACHE_DIR.is_dir(), reason="the local model is not downloaded here")
def test_the_downloaded_model_is_the_pinned_one():
    assert embedding.local_model_problem(str(embedding.DEFAULT_CACHE_DIR)) is None
