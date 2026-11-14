"""Database timeouts, outage reporting and connection pools (DB-1: DB-03 and DB-04). No database needed."""

import time
import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.app.db import data_plane
from backend.app.db.session import separate_runtime_engine
from backend.app.db.tls import connect_args

pytestmark = pytest.mark.unit

UNROUTABLE = "postgresql+pg8000://nobody:nothing@10.255.255.1:5432/nowhere"


def test_request_engines_get_a_socket_timeout_and_the_owner_engine_does_not(monkeypatch):
    monkeypatch.delenv("MDARIX_DB_SOCKET_TIMEOUT_SECONDS", raising=False)
    assert connect_args(request_path=True)["timeout"] == 75
    assert "timeout" not in connect_args()
    monkeypatch.setenv("MDARIX_DB_SOCKET_TIMEOUT_SECONDS", "5")
    assert connect_args(request_path=True)["timeout"] == 5


def test_one_control_pool_when_the_runtime_login_is_the_owner():
    assert separate_runtime_engine("mdarix_runtime", "mdarix_app") is True
    assert separate_runtime_engine("mdarix_app", "mdarix_app") is False
    assert separate_runtime_engine("", "mdarix_app") is False


@pytest.fixture
def fresh_planes():
    data_plane.session_factory.cache_clear()
    data_plane._SCHEMA_CHECKED.clear()
    yield
    data_plane.session_factory.cache_clear()
    data_plane._SCHEMA_CHECKED.clear()


def test_an_unreachable_plane_is_reported_unreachable_within_the_timeout_and_not_cached(monkeypatch, fresh_planes):
    monkeypatch.setenv("MDARIX_DB_SOCKET_TIMEOUT_SECONDS", "2")
    monkeypatch.setenv("MDARIX_DATA_PLANE_DB1_PROBE_DATABASE_URL", UNROUTABLE)
    started = time.monotonic()
    state = data_plane.plane_schema_state("db1-probe", "MDARIX_DATA_PLANE_DB1_PROBE_DATABASE_URL")
    assert state == data_plane.UNREACHABLE
    assert time.monotonic() - started < 10
    assert "db1-probe" not in data_plane._SCHEMA_CHECKED  # back in service as soon as it answers again


def test_a_request_to_an_unreachable_plane_gets_unavailable_not_being_upgraded(monkeypatch, fresh_planes):
    monkeypatch.setattr(data_plane, "plane_schema_state", lambda *_: data_plane.UNREACHABLE)
    row = SimpleNamespace(database_ref="db1-probe", connection_secret_ref="MDARIX_DATA_PLANE_DB1_PROBE_DATABASE_URL")
    monkeypatch.setenv("MDARIX_DATA_PLANE_DB1_PROBE_DATABASE_URL", UNROUTABLE)

    class Control:
        def query(self, *_):
            return self

        def filter(self, *_):
            return self

        def first(self):
            return row

    dependency = data_plane.get_data_plane_db(SimpleNamespace(tenant_id=str(uuid.uuid4())), Control())
    with pytest.raises(HTTPException) as refused:
        next(dependency)
    assert refused.value.status_code == 503
    assert refused.value.detail["code"] == "DATA_PLANE_UNAVAILABLE"


def test_an_outdated_plane_is_still_reported_as_being_upgraded(monkeypatch, fresh_planes):
    monkeypatch.setattr(data_plane, "plane_schema_state", lambda *_: data_plane.OUTDATED)
    row = SimpleNamespace(database_ref="db1-probe", connection_secret_ref="MDARIX_DATA_PLANE_DB1_PROBE_DATABASE_URL")
    monkeypatch.setenv("MDARIX_DATA_PLANE_DB1_PROBE_DATABASE_URL", UNROUTABLE)

    class Control:
        def query(self, *_):
            return self

        def filter(self, *_):
            return self

        def first(self):
            return row

    with pytest.raises(HTTPException) as refused:
        next(data_plane.get_data_plane_db(SimpleNamespace(tenant_id=str(uuid.uuid4())), Control()))
    assert refused.value.detail["code"] == "DATA_PLANE_SCHEMA_OUTDATED"


def test_a_plane_engine_pushed_out_of_the_cache_is_disposed(monkeypatch, fresh_planes):
    disposed = []

    class Engine:
        def __init__(self, ref):
            self.ref = ref

        def dispose(self):
            disposed.append(self.ref)

    monkeypatch.setattr(data_plane, "PLANE_ENGINE_CACHE", 2)
    monkeypatch.setattr(data_plane, "_new_session_factory", lambda ref: SimpleNamespace(kw={"bind": Engine(ref)}))
    first = data_plane.session_factory("a", "A")
    data_plane.session_factory("b", "B")
    assert data_plane.session_factory("a", "A") is first  # a hit keeps "a" recent
    data_plane.session_factory("c", "C")
    assert disposed == ["B"]
