"""MCP server — wraps every tool in :mod:`bus_mcp.tools` with the
``FastMCP`` decorator. The server reads the registry + gate from the
closure so the CLI can swap them out without touching this file.

Tools whose underlying driver call may block for a meaningful amount
of time (``can_receive`` waits on a SocketCAN socket; ``serial_receive``
waits on a UART; ``i2c_scan`` probes ~117 addresses) are declared
``async def`` and dispatched to a worker thread via
``asyncio.to_thread``. Without this, a single blocked receive call
would freeze the FastMCP event loop and queue every other inbound
JSON-RPC call behind it — making concurrent ``can_send`` /
``can_receive`` impossible from one MCP client."""

from __future__ import annotations

import asyncio
from typing import Any

from mcp.server.fastmcp import FastMCP

from . import tools
from .registry import BusRegistry
from .safety import WriteGate


def build_server(
    registry: BusRegistry,
    gate: WriteGate,
    *,
    host: str = "127.0.0.1",
    port: int = 7820,
) -> FastMCP:
    mcp = FastMCP("bus-mcp", host=host, port=port)

    # ── Meta ─────────────────────────────────────────────────────────────

    @mcp.tool()
    def bus_list() -> list[dict[str, str]]:
        """List every bus the host advertises.

        Each entry has ``bus_id`` (use this to address the bus from other
        tools), ``kind`` (``can`` / ``serial`` / ``i2c`` / ``spi`` /
        ``gpio``), and ``device`` (the underlying ``/dev`` path or
        SocketCAN iface name)."""
        return tools.bus_list(registry)

    @mcp.tool()
    def write_permissions() -> dict[str, list[str]]:
        """Show which bus kinds the operator has unlocked for writes.

        Empty list means everything is read-only — the operator must
        restart ``bus-mcp`` with ``--allow-write`` to enable sends."""
        return tools.write_permissions(gate)

    @mcp.tool()
    def bus_status(bus_id: str) -> dict[str, Any]:
        """Show the bus descriptor + stored config without opening it."""
        return tools.bus_status(registry, bus_id)

    @mcp.tool()
    def bus_close(bus_id: str) -> dict[str, Any]:
        """Release an open bus so its underlying driver is dropped.

        Use this after a ``can_configure`` / ``serial_configure`` call if
        you want the next send to pick up the new config without sending
        a dummy frame first."""
        return tools.bus_close(registry, bus_id)

    # ── CAN ──────────────────────────────────────────────────────────────

    @mcp.tool()
    def can_configure(
        bus_id: str,
        bitrate: int | None = None,
        fd: bool | None = None,
        data_bitrate: int | None = None,
        restart_ms: int | None = None,
        receive_own_messages: bool | None = None,
    ) -> dict[str, Any]:
        """Set CAN per-bus config. Fields you omit keep their current
        value. The bus is closed so the next send/receive opens with the
        new params — typical use is to retune ``bitrate`` mid-session."""
        return tools.can_configure(
            registry,
            bus_id,
            bitrate=bitrate,
            fd=fd,
            data_bitrate=data_bitrate,
            restart_ms=restart_ms,
            receive_own_messages=receive_own_messages,
        )

    @mcp.tool()
    def can_send(
        bus_id: str,
        arbitration_id: int,
        data_hex: str,
        is_extended_id: bool = False,
        is_fd: bool = False,
        bitrate_switch: bool = False,
    ) -> dict[str, Any]:
        """Transmit a CAN / CAN-FD frame.

        ``data_hex`` is a hex string (e.g. ``"deadbeef"``). Up to 8 bytes
        for classic CAN, 64 for CAN-FD. ``bitrate_switch`` is the FD BRS
        flag — only honoured when the bus is opened with ``fd=True`` and
        a ``data_bitrate`` is set."""
        return tools.can_send(
            registry,
            gate,
            bus_id,
            arbitration_id,
            data_hex,
            is_extended_id=is_extended_id,
            is_fd=is_fd,
            bitrate_switch=bitrate_switch,
        )

    @mcp.tool()
    async def can_receive(
        bus_id: str,
        timeout_s: float = 1.0,
        count: int = 10,
        can_id_filter: int | None = None,
        mask: int | None = None,
        extended: bool = False,
    ) -> list[dict[str, Any]]:
        """Drain up to ``count`` CAN frames or stop on the first
        ``timeout_s`` window with no frame.

        Optional single-filter convenience: pass ``can_id_filter`` (and
        optionally ``mask``) to push a SocketCAN filter to the kernel so
        unmatched frames never wake userspace. The filter is cleared
        after the call returns."""
        return await asyncio.to_thread(
            tools.can_receive,
            registry,
            bus_id,
            timeout_s=timeout_s,
            count=count,
            can_id_filter=can_id_filter,
            mask=mask,
            extended=extended,
        )

    # ── Serial ───────────────────────────────────────────────────────────

    @mcp.tool()
    def serial_configure(
        bus_id: str,
        baudrate: int | None = None,
        bytesize: int | None = None,
        parity: str | None = None,
        stopbits: float | None = None,
        timeout_s: float | None = None,
        rtscts: bool | None = None,
        dsrdtr: bool | None = None,
        xonxoff: bool | None = None,
    ) -> dict[str, Any]:
        """Reconfigure a serial bus. ``parity`` is ``N``/``E``/``O``/``M``/
        ``S`` (or ``NONE``/``EVEN``/``ODD``). ``bytesize`` is 5/6/7/8;
        ``stopbits`` is 1, 1.5, or 2."""
        return tools.serial_configure(
            registry,
            bus_id,
            baudrate=baudrate,
            bytesize=bytesize,
            parity=parity,
            stopbits=stopbits,
            timeout_s=timeout_s,
            rtscts=rtscts,
            dsrdtr=dsrdtr,
            xonxoff=xonxoff,
        )

    @mcp.tool()
    def serial_send(bus_id: str, data_hex: str) -> dict[str, Any]:
        """Write hex-encoded bytes to a UART / RS485 port."""
        return tools.serial_send(registry, gate, bus_id, data_hex)

    @mcp.tool()
    async def serial_receive(
        bus_id: str,
        max_bytes: int = 1024,
        timeout_s: float = 0.5,
    ) -> dict[str, Any]:
        """Read up to ``max_bytes`` from a UART / RS485 port."""
        return await asyncio.to_thread(
            tools.serial_receive,
            registry,
            bus_id,
            max_bytes=max_bytes,
            timeout_s=timeout_s,
        )

    # ── I2C ──────────────────────────────────────────────────────────────

    @mcp.tool()
    def i2c_read(
        bus_id: str,
        address: int,
        register: int,
        length: int,
    ) -> dict[str, Any]:
        """Read ``length`` bytes from an I2C device's register."""
        return tools.i2c_read(registry, bus_id, address, register, length)

    @mcp.tool()
    def i2c_write(
        bus_id: str,
        address: int,
        register: int,
        data_hex: str,
    ) -> dict[str, Any]:
        """Write hex-encoded bytes to an I2C device's register."""
        return tools.i2c_write(registry, gate, bus_id, address, register, data_hex)

    @mcp.tool()
    async def i2c_scan(
        bus_id: str,
        start: int = 0x03,
        end: int = 0x77,
    ) -> dict[str, Any]:
        """Probe every 7-bit address for an ACK (``i2cdetect``-equivalent).

        Returns the list of addresses that ACK'd. Counts as a write
        because each probe transmits a START + address byte."""
        return await asyncio.to_thread(
            tools.i2c_scan, registry, gate, bus_id, start=start, end=end
        )

    # ── SPI ──────────────────────────────────────────────────────────────

    @mcp.tool()
    def spi_configure(
        bus_id: str,
        max_speed_hz: int | None = None,
        mode: int | None = None,
        bits_per_word: int | None = None,
        lsb_first: bool | None = None,
        cs_high: bool | None = None,
    ) -> dict[str, Any]:
        """Reconfigure a SPI bus. ``mode`` is 0..3 (CPOL × CPHA);
        ``bits_per_word`` is the word size."""
        return tools.spi_configure(
            registry,
            bus_id,
            max_speed_hz=max_speed_hz,
            mode=mode,
            bits_per_word=bits_per_word,
            lsb_first=lsb_first,
            cs_high=cs_high,
        )

    @mcp.tool()
    def spi_xfer(
        bus_id: str,
        tx_hex: str,
        speed_hz: int | None = None,
    ) -> dict[str, Any]:
        """Full-duplex SPI transfer. Returns the RX bytes clocked in
        while the TX bytes were clocked out.

        Optional ``speed_hz`` overrides the bus default for just this
        call — handy for peripherals that want a slower clock for
        config writes than for data."""
        return tools.spi_xfer(registry, gate, bus_id, tx_hex, speed_hz=speed_hz)

    # ── GPIO ─────────────────────────────────────────────────────────────

    @mcp.tool()
    def gpio_configure(
        bus_id: str,
        pin: int,
        direction: str,
        pull: str = "none",
        active_low: bool = False,
        debounce_us: int = 0,
    ) -> dict[str, Any]:
        """Configure a GPIO pin.

        - ``direction``: ``"in"`` or ``"out"``.
        - ``pull``: ``"none"`` / ``"up"`` / ``"down"``.
        - ``active_low``: invert the logic level (useful for switches
          tied to ground).
        - ``debounce_us``: kernel-side debounce for inputs (0 = off)."""
        return tools.gpio_configure(
            registry,
            bus_id,
            pin,
            direction,
            pull=pull,
            active_low=active_low,
            debounce_us=debounce_us,
        )

    @mcp.tool()
    def gpio_read(bus_id: str, pin: int) -> dict[str, Any]:
        """Read a GPIO pin (returns ``{"pin": …, "value": 0|1}``)."""
        return tools.gpio_read(registry, bus_id, pin)

    @mcp.tool()
    def gpio_write(bus_id: str, pin: int, value: int) -> dict[str, Any]:
        """Drive a GPIO pin high (``value=1``) or low (``value=0``)."""
        return tools.gpio_write(registry, gate, bus_id, pin, value)

    return mcp
