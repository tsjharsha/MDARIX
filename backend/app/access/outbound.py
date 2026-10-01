"""Outbound requests to customer-configured connector endpoints.

A tenant administrator chooses a connector's URL, so every request is treated as hostile input:
- only http(s), no credentials in the URL;
- private, loopback, link-local, reserved and multicast addresses are refused unless the host is explicitly listed in
  MDARIX_CONNECTOR_ALLOWED_HOSTS (for example local simulators: "127.0.0.1:8101,localhost:8101");
- redirects are never followed, so a public address cannot bounce a request to an internal one;
- the address is checked again on the open socket, which defeats DNS rebinding between the check and the connect.
"""

from __future__ import annotations

import http.client
import ipaddress
import os
import re
from urllib.request import HTTPHandler, HTTPRedirectHandler, HTTPSHandler, Request, build_opener

# Connectors may only reference secrets in this namespace, never database, AI, email or session secrets.
CONNECTOR_SECRET_PREFIX = "MDARIX_CONNECTOR_SECRET_"
_SECRET_NAME = re.compile(r"^MDARIX_CONNECTOR_SECRET_[A-Z0-9_]{1,80}$")


def is_allowed_secret_ref(name: object) -> bool:
    return isinstance(name, str) and bool(_SECRET_NAME.match(name))


def _allowed_hosts() -> set[str]:
    raw = os.getenv("MDARIX_CONNECTOR_ALLOWED_HOSTS", "")
    return {item.strip().lower() for item in raw.split(",") if item.strip()}


def host_is_allowlisted(host: str, port: int | None) -> bool:
    allowed = _allowed_hosts()
    host = host.lower().rstrip(".")
    return host in allowed or (port is not None and f"{host}:{port}" in allowed)


def address_is_public(address: str) -> bool:
    ip = ipaddress.ip_address(address.split("%", 1)[0])
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return not (
        ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified
    )


class ConnectorDestinationBlocked(OSError):
    """Raised when a connection would reach a non-public address that is not allowlisted."""


def _check_peer(connection: http.client.HTTPConnection) -> None:
    peer = connection.sock.getpeername()[0] if connection.sock else None
    if peer is None or (not address_is_public(peer) and not host_is_allowlisted(connection.host, connection.port)):
        connection.close()
        raise ConnectorDestinationBlocked("CONNECTOR_PRIVATE_DESTINATION_BLOCKED")


class _CheckedHTTPConnection(http.client.HTTPConnection):
    def connect(self):
        super().connect()
        _check_peer(self)


class _CheckedHTTPSConnection(http.client.HTTPSConnection):
    def connect(self):
        super().connect()
        _check_peer(self)


class _CheckedHTTPHandler(HTTPHandler):
    def http_open(self, req):
        return self.do_open(_CheckedHTTPConnection, req)


class _CheckedHTTPSHandler(HTTPSHandler):
    def https_open(self, req):
        return self.do_open(_CheckedHTTPSConnection, req, context=self._context)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # the 3xx response is returned to the caller as an error, never followed


_OPENER = build_opener(_NoRedirect(), _CheckedHTTPHandler(), _CheckedHTTPSHandler())


def safe_urlopen(request: Request, timeout: float):
    """Open a connector request with the destination policy enforced on the live connection."""
    return _OPENER.open(request, timeout=timeout)
