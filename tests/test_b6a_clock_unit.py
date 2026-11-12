"""B6a Part A, G19 (B6-10, B6-11) and the deadline list's PDF paging (B6-06): offset maths with a fake clock; 0.9 s ok,
1.1 s degraded; a time server that cannot be reached is unknown, never ok; the alert fires once and clears once; the
printed list is one page per 40 lines."""

from __future__ import annotations

import socket
import struct
import threading

import pytest

from backend.app import clock_check

# B6b B3: the scenarios this file verifies (requirements.csv, class A); file level, so every test here carries them.
pytestmark = [pytest.mark.unit, pytest.mark.requirement("B6-10", "B6-11")]


class _Connection:
    def __init__(self, database_time: float):
        self.database_time = database_time

    def execute(self, _statement):
        return self

    def scalar_one(self):
        return self.database_time


def test_database_offset_uses_the_middle_of_the_round_trip():
    ticks = iter([100.0, 100.4])  # the query took 0.4 s
    offset = clock_check.database_offset(_Connection(100.9), clock=lambda: next(ticks))
    assert offset == pytest.approx(0.7)  # 100.9 - 100.2


@pytest.mark.parametrize(
    ("database", "ntp", "server", "state"),
    [
        (0.9, None, None, clock_check.OK),
        (-0.9, 0.95, "time.example", clock_check.OK),
        (1.1, None, None, clock_check.DEGRADED),
        (0.1, -1.1, "time.example", clock_check.DEGRADED),
        (0.1, None, "time.example", clock_check.UNKNOWN),  # the time server cannot be reached
        (None, None, None, clock_check.UNKNOWN),  # the database cannot be read
        (None, 2.0, "time.example", clock_check.DEGRADED),
    ],
)
def test_the_limit_is_one_second_and_unknown_is_never_ok(database, ntp, server, state):
    assert clock_check.assess(database, ntp, server)["state"] == state


def _answer(offset: float, now: float) -> bytes:
    def stamp(value: float) -> bytes:
        value += 2208988800
        return struct.pack("!II", int(value), int((value % 1) * 2**32))

    return b"\x1c\x02" + 30 * b"\0" + stamp(now + offset) + stamp(now + offset)


def test_sntp_offset_against_a_local_time_server():
    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.bind(("127.0.0.1", 0))
    port = server.getsockname()[1]

    def serve():
        _, client = server.recvfrom(64)
        server.sendto(_answer(3.0, 1000.0), client)

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        assert clock_check.sntp_offset(f"127.0.0.1:{port}", clock=lambda: 1000.0) == pytest.approx(3.0, abs=1e-6)
    finally:
        thread.join(2)
        server.close()


def test_an_unsynchronized_time_server_is_not_believed(monkeypatch):
    unsynchronized = bytes([0xDC, 0x02]) + _answer(5.0, 1000.0)[2:]  # leap indicator 3: the server's clock is not set

    class _Socket:
        def __init__(self, *args):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def settimeout(self, _):
            pass

        def sendto(self, *args):
            pass

        def recvfrom(self, _):
            return unsynchronized, None

    monkeypatch.setattr(clock_check.socket, "socket", _Socket)
    assert clock_check.sntp_offset("time.example") is None


def test_a_time_server_that_does_not_answer_is_unknown():
    silent = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    silent.bind(("127.0.0.1", 0))
    try:
        assert clock_check.sntp_offset(f"127.0.0.1:{silent.getsockname()[1]}", timeout=0.2) is None
    finally:
        silent.close()


def test_the_alert_fires_once_and_clears_once():
    sent: list[tuple[str, str]] = []
    state: dict = {}

    def result(database, at):
        return {**clock_check.assess(database, None, None), "checked_at": at}

    clock_check.alert(state, result(0.2, "2026-11-11T06:00:00+00:00"), lambda *alert: sent.append(alert))
    assert sent == [] and state["clock_good_at"] == "2026-11-11T06:00:00+00:00"
    clock_check.alert(state, result(1.5, "2026-11-11T06:05:00+00:00"), lambda *alert: sent.append(alert))
    clock_check.alert(state, result(1.6, "2026-11-11T06:10:00+00:00"), lambda *alert: sent.append(alert))
    assert [title for title, _ in sent] == ["Clock out of step"]
    assert "since 2026-11-11T06:00:00+00:00" in sent[0][1] and "never re-timed" in sent[0][1]
    clock_check.alert(state, result(0.1, "2026-11-11T06:15:00+00:00"), lambda *alert: sent.append(alert))
    clock_check.alert(state, result(0.1, "2026-11-11T06:20:00+00:00"), lambda *alert: sent.append(alert))
    assert [title for title, _ in sent] == ["Clock out of step", "Clock back in step"]


def test_the_printed_list_is_one_page_per_forty_lines():
    from backend.app.oversight import deadline_list

    found = {"day": "2026-11-11", "as_of": "2026-11-11T06:00:00+00:00", "zone": "Asia/Kolkata"}
    row = {
        "ref": "SAMPLE-RV-10",
        "market": "India (CDSCO)",
        "owed": "India report",
        "due_at": None,
        "due_label": "26 Nov 2026, 23:59 IST",
        "state": "LATER",
        "state_label": "Later",
        "owner": "",
    }
    for count, pages in ((0, 1), (40, 1), (41, 2), (85, 3)):
        body = deadline_list.as_pdf(found, [row] * count, "Orbit Medical Devices India (Sample)")
        assert body.count(b"/Type /Page") - body.count(b"/Type /Pages") == pages, count
