"""Uploaded files are virus-scanned by ClamAV (clamd INSTREAM); no clean verdict means the file is refused."""

import socket
import struct
import threading

import pytest

from object_storage.service import ObjectStorageService


class FakeClamd:
    """Answers one INSTREAM request: FOUND when the stream contains the EICAR marker, else OK."""

    def __init__(self):
        self.server = socket.socket()
        self.server.bind(("127.0.0.1", 0))
        self.server.listen(1)
        self.port = self.server.getsockname()[1]
        self.received = b""
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _read_exact(self, conn, size):
        data = b""
        while len(data) < size:
            part = conn.recv(size - len(data))
            if not part:
                raise ConnectionError
            data += part
        return data

    def _serve(self):
        conn, _ = self.server.accept()
        with conn:
            command = b""
            while not command.endswith(bytes([0])):
                command += conn.recv(1)
            assert command == b"zINSTREAM" + bytes([0])
            while True:
                (length,) = struct.unpack("!I", self._read_exact(conn, 4))
                if length == 0:
                    break
                self.received += self._read_exact(conn, length)
            verdict = b"stream: Eicar-Test-Signature FOUND" if b"EICAR" in self.received else b"stream: OK"
            conn.sendall(verdict + bytes([0]))
        self.server.close()


@pytest.fixture
def clamd(monkeypatch):
    fake = FakeClamd()
    monkeypatch.setenv("MDARIX_CLAMD_HOST", "127.0.0.1")
    monkeypatch.setenv("MDARIX_CLAMD_PORT", str(fake.port))
    return fake


def test_a_clean_file_passes_and_is_streamed_whole(clamd, tmp_path):
    content = b"lot,complaint\n" * 20000  # more than one 64 KiB chunk
    assert ObjectStorageService(str(tmp_path)).scan(content, "text/csv") is True
    clamd.thread.join(timeout=5)
    assert clamd.received == content


def test_an_infected_file_is_refused(clamd, tmp_path):
    assert ObjectStorageService(str(tmp_path)).scan(b"X5O!P%@AP EICAR test", "text/plain") is False


def test_an_unreachable_scanner_refuses_the_file(monkeypatch, tmp_path):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        free_port = probe.getsockname()[1]
    monkeypatch.setenv("MDARIX_CLAMD_HOST", "127.0.0.1")
    monkeypatch.setenv("MDARIX_CLAMD_PORT", str(free_port))
    monkeypatch.setenv("MDARIX_CLAMD_TIMEOUT_SECONDS", "2")
    assert ObjectStorageService(str(tmp_path)).scan(b"anything", "text/plain") is False
