"""Review O3: the local text log's request line carries its duration, as the JSON log does."""

import logging

import pytest

from backend.app.logging_setup import TextFormatter

pytestmark = pytest.mark.unit


def test_the_request_line_ends_with_its_duration():
    record = logging.LogRecord("mdarix.api", logging.INFO, __file__, 1, "GET /api/v1/trial/story 200", None, None)
    record.duration_ms = 123.4
    assert TextFormatter("%(message)s").format(record) == "GET /api/v1/trial/story 200 123.4ms"
    plain = logging.LogRecord("x", logging.INFO, __file__, 1, "no request", None, None)
    assert TextFormatter("%(message)s").format(plain) == "no request"
