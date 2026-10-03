"""The address of the client that sent a request, safe to use for rate limits and audit records.

Behind reverse proxies, ``X-Forwarded-For`` lists addresses left to right; each proxy appends the address it received
the request from. Only the entries our own proxies appended can be trusted: anything further left was written by the
client and may be forged. With ``MDARIX_TRUSTED_PROXY_HOPS=N`` (the number of proxies in front of the API, usually 1
for Caddy), the client is the N-th address from the right. With 0 (the default) the header is ignored and the
socket peer is used, which is correct when the API is not behind a proxy or uvicorn already rewrote the peer
(``--proxy-headers --forwarded-allow-ips``).

``MDARIX_TRUST_PROXY_HEADERS=true`` (older setting) means one trusted proxy.
"""

from __future__ import annotations

import ipaddress
import os

from starlette.requests import Request


def trusted_proxy_hops() -> int:
    raw = os.getenv("MDARIX_TRUSTED_PROXY_HOPS", "").strip()
    if raw:
        try:
            return max(0, min(int(raw), 5))
        except ValueError:
            return 0
    return 1 if os.getenv("MDARIX_TRUST_PROXY_HEADERS", "").strip().lower() in {"1", "true", "yes"} else 0


def _valid(address: str) -> str | None:
    try:
        return str(ipaddress.ip_address(address.strip().strip("[]")))
    except ValueError:
        return None


def client_ip(request: Request) -> str | None:
    """The client's IP address, or None when it is unknown (for example in a unit test without a socket)."""
    peer = request.client.host if request.client else None
    hops = trusted_proxy_hops()
    if hops:
        forwarded = [item.strip() for item in request.headers.get("x-forwarded-for", "").split(",") if item.strip()]
        if len(forwarded) >= hops:
            candidate = _valid(forwarded[-hops])
            if candidate:
                return candidate
    return _valid(peer) if peer else None
