"""Put the server's trial AI gateways on the API's own 127.0.0.1 (docker-compose.prod.yml).

    python scripts/ai_loopback_forwarder.py --forward 3011=10.99.211.1:3011 --forward 20128=10.99.211.1:20128

In staging and production MDARIX calls FreeLLMAPI and OmniRoute only at 127.0.0.1 (genai/provider.py,
trial_chain_problems): the gateways run on the same server, bound to the host's 127.0.0.1, and are never on a network.
Inside a container 127.0.0.1 is the container itself, so two copies of this process bridge the gap without changing
that rule:
  - ai-loopback-api and ai-loopback-background share the network namespace of the API and of the background service
    and listen on its 127.0.0.1 only (the default --listen); each connection goes to the ai-host network's gateway.
  - ai-host-bridge runs in the host's network namespace with --listen set to that gateway address, a private address
    on the host's own bridge (never 0.0.0.0, never a public address), and passes each connection to the gateway on the
    host's 127.0.0.1.
The API's addresses stay http://127.0.0.1:3011 and http://127.0.0.1:20128 and the loopback check is unchanged. When a
gateway is not running, each connection is closed at once and the trial chain moves on to its next provider.
(The same process served the Windows laptop demo through host.docker.internal.)
"""

from __future__ import annotations

import argparse
import asyncio
import ipaddress
import logging
import sys

# The default: the forwarded ports are reachable from inside this network namespace only.
LISTEN_HOST = "127.0.0.1"
CONNECT_TIMEOUT_SECONDS = 5.0
logger = logging.getLogger("ai-loopback-forwarder")


def parse_forward(spec: str) -> tuple[int, str, int]:
    """``LISTEN_PORT=HOST:PORT`` as (listen port, host, port)."""
    listen, _, target = spec.partition("=")
    host, _, port = target.rpartition(":")
    if not listen.isdigit() or not port.isdigit() or not host:
        raise argparse.ArgumentTypeError(f"expected LISTEN_PORT=HOST:PORT, got {spec!r}")
    return int(listen), host, int(port)


def parse_listen(value: str) -> str:
    """A loopback or private (RFC 1918) address only: a public address would open the gateways to the network."""
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"--listen must be an IP address, got {value!r}") from None
    if not (address.is_loopback or (address.is_private and not address.is_unspecified)):
        raise argparse.ArgumentTypeError(f"--listen must be a loopback or private address, got {value}")
    return value


async def _pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while data := await reader.read(65536):
            writer.write(data)
            await writer.drain()
        if writer.can_write_eof():
            writer.write_eof()  # half-close: the other direction may still be answering
    except OSError:
        pass


def _handler(host: str, port: int):
    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            up_reader, up_writer = await asyncio.wait_for(asyncio.open_connection(host, port), CONNECT_TIMEOUT_SECONDS)
        except (OSError, TimeoutError) as exc:
            # The gateway is not running: the API sees a refused call and its chain moves on.
            logger.warning("gateway %s:%s not reachable (%s)", host, port, type(exc).__name__)
            writer.close()
            return
        try:
            await asyncio.gather(_pipe(reader, up_writer), _pipe(up_reader, writer))
        finally:
            for side in (writer, up_writer):
                side.close()

    return handle


async def serve(
    forwards: list[tuple[int, str, int]], ready: asyncio.Event | None = None, listen_host: str = LISTEN_HOST
) -> None:
    servers = [await asyncio.start_server(_handler(h, p), listen_host, lp) for lp, h, p in forwards]
    for listen, host, port in forwards:
        logger.info("forwarding %s:%s to %s:%s", listen_host, listen, host, port)
    if ready:
        ready.set()
    try:
        await asyncio.gather(*(server.serve_forever() for server in servers))
    finally:
        for server in servers:
            server.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--forward", action="append", type=parse_forward, required=True)
    parser.add_argument("--listen", type=parse_listen, default=LISTEN_HOST)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s", stream=sys.stdout)
    try:
        asyncio.run(serve(args.forward, listen_host=args.listen))
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
