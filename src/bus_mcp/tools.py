"""Tool implementations — pure functions over (registry, gate, args).

The MCP server (:mod:`bus_mcp.server`) thinly wraps each one in
``@mcp.tool()`` so unit tests can exercise the full behaviour without an
MCP client. Configure tools update the registry's per-bus kwargs map and
close the bus so the next call opens it with the new config.
"""

from __future__ import annotations

from typing import Any

from .registry import BusRegistry
from .safety import WriteGate


# ---------------------------------------------------------------------------
# Meta
# ---------------------------------------------------------------------------


def bus_list(registry: BusRegistry) -> list[dict[str, str]]:
    return [
        {"bus_id": b.bus_id, "kind": b.kind, "device": b.device}
        for b in registry.list()
    ]


def write_permissions(gate: WriteGate) -> dict[str, list[str]]:
    return {"allowed": sorted(gate.allowed)}


def bus_close(registry: BusRegistry, bus_id: str) -> dict[str, Any]:
    """Release a bus the agent opened earlier. The next tool call against
    it will reopen it with the current config."""
    closed = registry.close(bus_id)
    return {"closed": closed, "bus_id": bus_id}


def bus_status(registry: BusRegistry, bus_id: str) -> dict[str, Any]:
    """Show stored config (no driver invocation — won't open the bus)."""
    descriptor = registry.get(bus_id)
    return {
        "bus_id": descriptor.bus_id,
        "kind": descriptor.kind,
        "device": descriptor.device,
        "config": registry.get_config(bus_id),
    }


# ---------------------------------------------------------------------------
# CAN
# ---------------------------------------------------------------------------


def can_configure(
    registry: BusRegistry,
    bus_id: str,
    *,
    bitrate: int | None = None,
    fd: bool | None = None,
    data_bitrate: int | None = None,
    restart_ms: int | None = None,
    receive_own_messages: bool | None = None,
) -> dict[str, Any]:
    """Set per-bus CAN config. Keeps fields not passed at their current
    value. Closes the bus so the next send/receive opens with the new
    config — useful for retuning bitrate during exploration."""
    cfg: dict[str, Any] = {}
    if bitrate is not None:
        cfg["bitrate"] = int(bitrate)
    if fd is not None:
        cfg["fd"] = bool(fd)
    if data_bitrate is not None:
        cfg["data_bitrate"] = int(data_bitrate)
    if restart_ms is not None:
        cfg["restart_ms"] = int(restart_ms)
    if receive_own_messages is not None:
        cfg["receive_own_messages"] = bool(receive_own_messages)
    merged = registry.set_config(bus_id, cfg)
    return {"bus_id": bus_id, "config": merged}


def can_send(
    registry: BusRegistry,
    gate: WriteGate,
    bus_id: str,
    arbitration_id: int,
    data_hex: str,
    *,
    is_extended_id: bool = False,
    is_fd: bool = False,
    bitrate_switch: bool = False,
) -> dict[str, Any]:
    gate.check("can")
    bus = registry.open(bus_id)
    bus.send(
        arbitration_id,
        bytes.fromhex(data_hex),
        is_extended_id=is_extended_id,
        is_fd=is_fd,
        bitrate_switch=bitrate_switch,
    )
    return {
        "sent": True,
        "bus_id": bus_id,
        "arbitration_id": arbitration_id,
        "bytes": len(data_hex) // 2,
    }


def can_receive(
    registry: BusRegistry,
    bus_id: str,
    *,
    timeout_s: float = 1.0,
    count: int = 10,
    can_id_filter: int | None = None,
    mask: int | None = None,
    extended: bool = False,
) -> list[dict[str, Any]]:
    bus = registry.open(bus_id)
    return bus.receive(
        timeout_s=timeout_s,
        count=count,
        can_id_filter=can_id_filter,
        mask=mask,
        extended=extended,
    )


# ---------------------------------------------------------------------------
# Serial (UART / RS485)
# ---------------------------------------------------------------------------


def serial_configure(
    registry: BusRegistry,
    bus_id: str,
    *,
    baudrate: int | None = None,
    bytesize: int | None = None,
    parity: str | None = None,
    stopbits: float | None = None,
    timeout_s: float | None = None,
    rtscts: bool | None = None,
    dsrdtr: bool | None = None,
    xonxoff: bool | None = None,
) -> dict[str, Any]:
    cfg: dict[str, Any] = {}
    if baudrate is not None:
        cfg["baudrate"] = int(baudrate)
    if bytesize is not None:
        cfg["bytesize"] = int(bytesize)
    if parity is not None:
        cfg["parity"] = str(parity)
    if stopbits is not None:
        cfg["stopbits"] = float(stopbits)
    if timeout_s is not None:
        cfg["timeout_s"] = float(timeout_s)
    if rtscts is not None:
        cfg["rtscts"] = bool(rtscts)
    if dsrdtr is not None:
        cfg["dsrdtr"] = bool(dsrdtr)
    if xonxoff is not None:
        cfg["xonxoff"] = bool(xonxoff)
    merged = registry.set_config(bus_id, cfg)
    return {"bus_id": bus_id, "config": merged}


def serial_send(
    registry: BusRegistry,
    gate: WriteGate,
    bus_id: str,
    data_hex: str,
) -> dict[str, Any]:
    gate.check("serial")
    bus = registry.open(bus_id)
    n = bus.write(bytes.fromhex(data_hex))
    return {"sent_bytes": n, "bus_id": bus_id}


def serial_receive(
    registry: BusRegistry,
    bus_id: str,
    *,
    max_bytes: int = 1024,
    timeout_s: float = 0.5,
) -> dict[str, Any]:
    bus = registry.open(bus_id)
    data = bus.read(max_bytes=max_bytes, timeout_s=timeout_s)
    return {"data_hex": data.hex(), "bytes": len(data)}


# ---------------------------------------------------------------------------
# I2C
# ---------------------------------------------------------------------------


def i2c_read(
    registry: BusRegistry,
    bus_id: str,
    address: int,
    register: int,
    length: int,
) -> dict[str, Any]:
    bus = registry.open(bus_id)
    data = bus.read(address, register, length)
    return {"data_hex": data.hex(), "bytes": len(data)}


def i2c_write(
    registry: BusRegistry,
    gate: WriteGate,
    bus_id: str,
    address: int,
    register: int,
    data_hex: str,
) -> dict[str, Any]:
    gate.check("i2c")
    bus = registry.open(bus_id)
    bus.write(address, register, bytes.fromhex(data_hex))
    return {
        "sent": True,
        "bus_id": bus_id,
        "address": address,
        "register": register,
        "bytes": len(data_hex) // 2,
    }


def i2c_scan(
    registry: BusRegistry,
    gate: WriteGate,
    bus_id: str,
    *,
    start: int = 0x03,
    end: int = 0x77,
) -> dict[str, Any]:
    """Probe every 7-bit address in [start, end] for an ACK. Equivalent
    to ``i2cdetect -y <bus>``. Counts as a write because each probe
    sends a START + address byte."""
    gate.check("i2c")
    bus = registry.open(bus_id)
    found: list[int] = []
    for addr in range(int(start), int(end) + 1):
        try:
            bus.write_quick(addr)
        except Exception:
            continue
        found.append(addr)
    return {
        "bus_id": bus_id,
        "found": found,
        "range": [int(start), int(end)],
    }


# ---------------------------------------------------------------------------
# SPI
# ---------------------------------------------------------------------------


def spi_configure(
    registry: BusRegistry,
    bus_id: str,
    *,
    max_speed_hz: int | None = None,
    mode: int | None = None,
    bits_per_word: int | None = None,
    lsb_first: bool | None = None,
    cs_high: bool | None = None,
) -> dict[str, Any]:
    cfg: dict[str, Any] = {}
    if max_speed_hz is not None:
        cfg["max_speed_hz"] = int(max_speed_hz)
    if mode is not None:
        cfg["mode"] = int(mode)
    if bits_per_word is not None:
        cfg["bits_per_word"] = int(bits_per_word)
    if lsb_first is not None:
        cfg["lsb_first"] = bool(lsb_first)
    if cs_high is not None:
        cfg["cs_high"] = bool(cs_high)
    merged = registry.set_config(bus_id, cfg)
    return {"bus_id": bus_id, "config": merged}


def spi_xfer(
    registry: BusRegistry,
    gate: WriteGate,
    bus_id: str,
    tx_hex: str,
    *,
    speed_hz: int | None = None,
) -> dict[str, Any]:
    # SPI is full-duplex — every TX clocks an RX. We gate on write
    # because most SPI peripherals act on the TX bytes even if the
    # caller "only wants to read."
    gate.check("spi")
    bus = registry.open(bus_id)
    rx = bus.xfer(bytes.fromhex(tx_hex), speed_hz=speed_hz)
    return {"rx_hex": rx.hex(), "bytes": len(rx)}


# ---------------------------------------------------------------------------
# GPIO
# ---------------------------------------------------------------------------


def gpio_configure(
    registry: BusRegistry,
    bus_id: str,
    pin: int,
    direction: str,
    *,
    pull: str = "none",
    active_low: bool = False,
    debounce_us: int = 0,
) -> dict[str, Any]:
    bus = registry.open(bus_id)
    bus.configure(
        pin,
        direction=direction,
        pull=pull,
        active_low=active_low,
        debounce_us=debounce_us,
    )
    return {
        "pin": pin,
        "direction": direction,
        "pull": pull,
        "active_low": active_low,
        "debounce_us": debounce_us,
    }


def gpio_read(
    registry: BusRegistry,
    bus_id: str,
    pin: int,
) -> dict[str, Any]:
    bus = registry.open(bus_id)
    return {"pin": pin, "value": int(bus.read(pin))}


def gpio_write(
    registry: BusRegistry,
    gate: WriteGate,
    bus_id: str,
    pin: int,
    value: int,
) -> dict[str, Any]:
    gate.check("gpio")
    bus = registry.open(bus_id)
    bus.write(pin, value)
    return {"pin": pin, "value": int(bool(value))}
