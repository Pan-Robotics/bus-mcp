"""``bus-mcp`` CLI.

Subcommands:
  - ``serve`` — run the MCP server (stdio or streamable-HTTP).
  - ``list``  — print discovered buses without opening them.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence

from . import __version__
from .discovery import discover_buses
from .registry import BusRegistry
from .safety import WriteGate, parse_allow_write


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="bus-mcp",
        description="MCP server exposing Raspberry Pi peripheral buses to AI agents.",
    )
    parser.add_argument(
        "--version", action="version", version=f"bus-mcp {__version__}"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    serve = sub.add_parser("serve", help="Run the MCP server")
    serve.add_argument(
        "--transport",
        choices=("stdio", "http"),
        default="stdio",
        help=(
            "MCP transport. ``stdio`` (default) for Claude Desktop / "
            "Claude Code. ``http`` for streamable-HTTP on --host:--port."
        ),
    )
    serve.add_argument(
        "--host",
        default="127.0.0.1",
        help="HTTP bind host (default 127.0.0.1 — localhost only).",
    )
    serve.add_argument(
        "--port",
        type=int,
        default=7820,
        help="HTTP bind port (default 7820).",
    )
    serve.add_argument(
        "--allow-write",
        nargs="?",
        const="*",
        default=None,
        metavar="BUSES",
        help=(
            "Enable write tools. Use the flag with no argument to allow every "
            "bus kind, or pass a comma-separated list (e.g. --allow-write=can,serial)."
        ),
    )
    serve.add_argument(
        "--log-level",
        default="info",
        choices=("debug", "info", "warning", "error"),
    )

    sub.add_parser("list", help="Show which buses this host advertises")

    args = parser.parse_args(argv)

    logging.basicConfig(
        level=(args.log_level.upper() if args.cmd == "serve" else "INFO"),
        format="%(asctime)s %(levelname)-5s %(name)s | %(message)s",
        stream=sys.stderr,
    )
    log = logging.getLogger("bus-mcp")

    discovered = discover_buses()
    if args.cmd == "list":
        if not discovered:
            print(
                "No buses discovered. Are you on a Pi with the relevant "
                "kernel modules loaded (i2c-dev, spidev, …)?"
            )
            return 0
        for b in discovered:
            print(f"{b.bus_id:24}  {b.kind:8}  {b.device}")
        return 0

    # ── serve ──────────────────────────────────────────────────────────
    registry = BusRegistry()
    for b in discovered:
        registry.register(b)
    log.info("registered %d bus(es)", len(registry.list()))

    gate = WriteGate(parse_allow_write(args.allow_write))
    if gate.allowed:
        log.info("write gate: ALLOW %s", ", ".join(sorted(gate.allowed)))
    else:
        log.info("write gate: read-only (use --allow-write to enable sends)")

    # Deferred — keeps `bus-mcp list` working when `mcp` isn't installed.
    from .server import build_server

    server = build_server(registry, gate, host=args.host, port=args.port)
    try:
        if args.transport == "stdio":
            server.run()  # FastMCP defaults to stdio
        else:
            log.info(
                "MCP HTTP listening on http://%s:%d/mcp",
                args.host,
                args.port,
            )
            server.run(transport="streamable-http")
    finally:
        registry.close_all()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
