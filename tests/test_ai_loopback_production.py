"""The trial AI gateways stay on loopback in production (docker-compose.prod.yml, scripts/ai_loopback_forwarder.py).

The API and the background service call FreeLLMAPI and OmniRoute at their own 127.0.0.1; forwarders carry those ports
to the host's 127.0.0.1 through a private bridge address, and nothing is published.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import ipaddress
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = yaml.safe_load((ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8"))
SERVICES = COMPOSE["services"]
SIDECARS = {"ai-loopback-api": "api", "ai-loopback-background": "background"}
GATEWAY_PORTS = {3011, 20128}

_spec = importlib.util.spec_from_file_location("ai_loopback_forwarder", ROOT / "scripts" / "ai_loopback_forwarder.py")
forwarder = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(forwarder)


def _args(service: dict) -> tuple[str, list[tuple[int, str, int]]]:
    command = service["command"]
    assert command[:2] == ["python", "scripts/ai_loopback_forwarder.py"]
    listen = forwarder.parse_listen(command[command.index("--listen") + 1]) if "--listen" in command else "127.0.0.1"
    forwards = [forwarder.parse_forward(command[i + 1]) for i, arg in enumerate(command) if arg == "--forward"]
    return listen, forwards


def _ai_host() -> tuple[ipaddress.IPv4Network, ipaddress.IPv4Address]:
    (config,) = COMPOSE["networks"]["ai-host"]["ipam"]["config"]
    return ipaddress.ip_network(config["subnet"]), ipaddress.ip_address(config["gateway"])


def test_the_host_bridge_listens_only_on_the_private_gateway_of_its_own_network():
    subnet, gateway = _ai_host()
    assert subnet.is_private and gateway in subnet
    # The existing network is untouched: changing its addressing would recreate it on the server.
    assert COMPOSE["networks"]["internal"] == {}
    bridge = SERVICES["ai-host-bridge"]
    assert bridge["network_mode"] == "host"
    listen, forwards = _args(bridge)
    assert ipaddress.ip_address(listen) == gateway
    assert forwards == [(port, "127.0.0.1", port) for port in sorted(GATEWAY_PORTS)]


def test_the_app_containers_reach_the_gateways_at_their_own_loopback():
    _, gateway = _ai_host()
    for sidecar, app in SIDECARS.items():
        service = SERVICES[sidecar]
        assert service["network_mode"] == f"service:{app}"
        listen, forwards = _args(service)
        assert listen == "127.0.0.1", sidecar
        assert {(lp, ipaddress.ip_address(host), port) for lp, host, port in forwards} == {
            (port, gateway, port) for port in GATEWAY_PORTS
        }
        # The sidecar shares the app's namespace, so the app must be on ai-host for the route to the gateway.
        assert "ai-host" in SERVICES[app]["networks"] and "internal" in SERVICES[app]["networks"]
        # No address override: the API keeps the built-in http://127.0.0.1:3011 and :20128 (genai/provider.py).
        environment = SERVICES[app].get("environment") or {}
        assert not [key for key in environment if "FREELLMAPI" in key or "OMNIROUTE" in key], app


@pytest.mark.parametrize("name", [*SIDECARS, "ai-host-bridge"])
def test_the_forwarders_publish_nothing_and_are_locked_down(name):
    service = SERVICES[name]
    assert "ports" not in service and "expose" not in service and "env_file" not in service
    assert service["read_only"] is True and service["cap_drop"] == ["ALL"]
    assert "no-new-privileges:true" in service["security_opt"]
    assert service["restart"] == "unless-stopped" and service["mem_limit"] == "64m"
    assert service["image"] == SERVICES["api"]["image"]


@pytest.mark.parametrize("value", ["0.0.0.0", "::", "8.8.8.8", "example.com"])
def test_the_forwarder_refuses_a_public_or_unspecified_listen_address(value):
    with pytest.raises(argparse.ArgumentTypeError):
        forwarder.parse_listen(value)
    with pytest.raises(SystemExit):
        forwarder.main(["--listen", value, "--forward", "3011=127.0.0.1:3011"])


@pytest.mark.parametrize("value", ["127.0.0.1", "::1", "10.99.211.1", "172.30.0.1", "192.168.1.1"])
def test_the_forwarder_accepts_a_loopback_or_private_listen_address(value):
    assert forwarder.parse_listen(value) == value


async def free_port() -> int:
    probe = await asyncio.start_server(lambda r, w: None, "127.0.0.1", 0)
    port = probe.sockets[0].getsockname()[1]
    probe.close()
    await probe.wait_closed()
    return port


def test_a_connection_is_forwarded_both_ways_and_a_missing_gateway_is_refused():
    async def scenario() -> None:
        async def echo(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            writer.write(b"echo:" + await reader.read())  # until the client's half-close
            await writer.drain()
            writer.close()

        upstream = await asyncio.start_server(echo, "127.0.0.1", 0)
        upstream_port = upstream.sockets[0].getsockname()[1]
        # A port with nothing behind it is the "gateway is not running" case.
        closed_port, *listen_ports = [await free_port() for _ in range(3)]

        ready = asyncio.Event()
        task = asyncio.create_task(
            forwarder.serve(
                [(listen_ports[0], "127.0.0.1", upstream_port), (listen_ports[1], "127.0.0.1", closed_port)], ready
            )
        )
        await asyncio.wait_for(ready.wait(), 5)
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", listen_ports[0])
            writer.write(b"GET /v1/models")
            writer.write_eof()
            assert await asyncio.wait_for(reader.read(), 5) == b"echo:GET /v1/models"
            writer.close()

            reader, writer = await asyncio.open_connection("127.0.0.1", listen_ports[1])
            assert await asyncio.wait_for(reader.read(), 10) == b""  # closed at once, nothing hangs
            writer.close()
        finally:
            task.cancel()
            upstream.close()
            await upstream.wait_closed()

    asyncio.run(scenario())
