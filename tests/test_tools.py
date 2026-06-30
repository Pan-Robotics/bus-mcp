"""End-to-end tests for the tool layer with hand-rolled bus fakes."""

from __future__ import annotations

from typing import Any

import pytest

from bus_mcp import tools
from bus_mcp.registry import BusRegistry, DiscoveredBus
from bus_mcp.safety import WriteGate


# ---------------------------------------------------------------------------
# Fakes — one per bus kind, exposing the methods tools.* expects.
# Factory signature is ``(device, config_dict)``.
# ---------------------------------------------------------------------------


class _FakeCan:
    def __init__(self, device: str, **config: Any) -> None:
        self.device = device
        self.config = config
        self.sent: list[dict[str, Any]] = []
        self.queued: list[dict[str, Any]] = []
        self.filters: list[dict[str, Any]] | None = None

    def send(
        self,
        arbitration_id: int,
        data: bytes,
        *,
        is_extended_id: bool = False,
        is_fd: bool = False,
        bitrate_switch: bool = False,
    ) -> None:
        self.sent.append(
            {
                "arbitration_id": arbitration_id,
                "data": bytes(data),
                "is_extended_id": is_extended_id,
                "is_fd": is_fd,
                "bitrate_switch": bitrate_switch,
            }
        )

    def receive(
        self,
        *,
        timeout_s: float,
        count: int,
        can_id_filter: int | None = None,
        mask: int | None = None,
        extended: bool = False,
    ) -> list[dict[str, Any]]:
        if can_id_filter is not None:
            self.filters = [
                {
                    "can_id": can_id_filter,
                    "can_mask": mask if mask is not None else 0x7FF,
                    "extended": extended,
                }
            ]
        out = self.queued[:count]
        self.queued = self.queued[count:]
        return out

    def close(self) -> None: ...


class _FakeSerial:
    def __init__(self, device: str, **config: Any) -> None:
        self.device = device
        self.config = config
        self.written = bytearray()
        self.buffered = bytearray()

    def write(self, data: bytes) -> int:
        self.written.extend(data)
        return len(data)

    def read(self, *, max_bytes: int, timeout_s: float) -> bytes:
        take = bytes(self.buffered[:max_bytes])
        del self.buffered[: len(take)]
        return take

    def close(self) -> None: ...


class _FakeI2c:
    def __init__(self, device: str, **config: Any) -> None:
        self.device = device
        self.config = config
        self.writes: list[tuple[int, int, bytes]] = []
        self.next_read: bytes = b""
        self.acks: set[int] = set()

    def read(self, address: int, register: int, length: int) -> bytes:
        return self.next_read[:length]

    def write(self, address: int, register: int, data: bytes) -> None:
        self.writes.append((address, register, bytes(data)))

    def write_quick(self, address: int) -> None:
        if address not in self.acks:
            raise OSError("NACK")

    def close(self) -> None: ...


class _FakeSpi:
    def __init__(self, device: str, **config: Any) -> None:
        self.device = device
        self.config = config
        self.last_tx: bytes = b""
        self.last_speed_hz: int | None = None
        self.next_rx: bytes = b""

    def xfer(self, tx: bytes, *, speed_hz: int | None = None) -> bytes:
        self.last_tx = bytes(tx)
        self.last_speed_hz = speed_hz
        return self.next_rx or bytes(len(tx))

    def close(self) -> None: ...


class _FakeGpio:
    def __init__(self, device: str, **config: Any) -> None:
        self.device = device
        self.config = config
        self.configured: list[dict[str, Any]] = []
        self.writes: list[tuple[int, int]] = []
        self.pin_values: dict[int, int] = {}

    def configure(
        self,
        pin: int,
        *,
        direction: str,
        pull: str = "none",
        active_low: bool = False,
        debounce_us: int = 0,
    ) -> None:
        self.configured.append(
            {
                "pin": pin,
                "direction": direction,
                "pull": pull,
                "active_low": active_low,
                "debounce_us": debounce_us,
            }
        )

    def read(self, pin: int) -> int:
        return self.pin_values.get(pin, 0)

    def write(self, pin: int, value: int) -> None:
        self.writes.append((pin, int(value)))
        self.pin_values[pin] = int(bool(value))

    def close(self) -> None: ...


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _factory(cls: type) -> Any:
    def factory(device: str, config: dict[str, Any]) -> Any:
        return cls(device, **config)

    return factory


@pytest.fixture
def registry() -> BusRegistry:
    r = BusRegistry(
        factories={
            "can": _factory(_FakeCan),
            "serial": _factory(_FakeSerial),
            "i2c": _factory(_FakeI2c),
            "spi": _factory(_FakeSpi),
            "gpio": _factory(_FakeGpio),
        }
    )
    r.register(DiscoveredBus("can_can0", "can", "can0"))
    r.register(DiscoveredBus("can_can1", "can", "can1"))
    r.register(DiscoveredBus("serial_ttyUSB0", "serial", "/dev/ttyUSB0"))
    r.register(DiscoveredBus("i2c_i2c-1", "i2c", "/dev/i2c-1"))
    r.register(DiscoveredBus("spi_spidev0.0", "spi", "/dev/spidev0.0"))
    r.register(DiscoveredBus("gpio_gpiochip0", "gpio", "/dev/gpiochip0"))
    return r


@pytest.fixture
def open_gate() -> WriteGate:
    return WriteGate({"can", "serial", "i2c", "spi", "gpio"})


@pytest.fixture
def closed_gate() -> WriteGate:
    return WriteGate(set())


# ---------------------------------------------------------------------------
# Meta tools
# ---------------------------------------------------------------------------


def test_bus_list_returns_every_registered_bus(registry: BusRegistry) -> None:
    out = tools.bus_list(registry)
    assert {b["bus_id"] for b in out} == {
        "can_can0",
        "can_can1",
        "serial_ttyUSB0",
        "i2c_i2c-1",
        "spi_spidev0.0",
        "gpio_gpiochip0",
    }


def test_write_permissions_reflects_gate_state(open_gate: WriteGate) -> None:
    assert tools.write_permissions(open_gate) == {
        "allowed": ["can", "gpio", "i2c", "serial", "spi"],
    }


def test_bus_status_returns_descriptor_and_config(registry: BusRegistry) -> None:
    tools.can_configure(registry, "can_can0", bitrate=250_000)
    status = tools.bus_status(registry, "can_can0")
    assert status["bus_id"] == "can_can0"
    assert status["kind"] == "can"
    assert status["device"] == "can0"
    assert status["config"]["bitrate"] == 250_000


def test_bus_close_releases_an_open_bus(registry: BusRegistry) -> None:
    registry.open("can_can0")
    out = tools.bus_close(registry, "can_can0")
    assert out == {"closed": True, "bus_id": "can_can0"}
    # Calling again returns False — nothing left to close.
    assert tools.bus_close(registry, "can_can0") == {"closed": False, "bus_id": "can_can0"}


# ---------------------------------------------------------------------------
# CAN
# ---------------------------------------------------------------------------


def test_can_configure_stores_kwargs_and_closes_bus(registry: BusRegistry) -> None:
    a = registry.open("can_can0")
    out = tools.can_configure(registry, "can_can0", bitrate=1_000_000, fd=True, data_bitrate=2_000_000)
    assert out["config"]["bitrate"] == 1_000_000
    assert out["config"]["fd"] is True
    assert out["config"]["data_bitrate"] == 2_000_000
    # The previously-open bus was closed; next open uses the new config.
    b = registry.open("can_can0")
    assert b is not a
    assert b.config == {"bitrate": 1_000_000, "fd": True, "data_bitrate": 2_000_000}


def test_can_configure_with_no_kwargs_is_a_noop(registry: BusRegistry) -> None:
    tools.can_configure(registry, "can_can0", bitrate=250_000)
    tools.can_configure(registry, "can_can0")  # nothing to change
    assert registry.get_config("can_can0") == {"bitrate": 250_000}


def test_can_send_forwards_frame_fields(
    registry: BusRegistry, open_gate: WriteGate
) -> None:
    result = tools.can_send(
        registry,
        open_gate,
        "can_can0",
        0x123,
        "deadbeef",
        is_extended_id=True,
        is_fd=True,
        bitrate_switch=True,
    )
    assert result == {
        "sent": True,
        "bus_id": "can_can0",
        "arbitration_id": 0x123,
        "bytes": 4,
    }
    fake: _FakeCan = registry.open("can_can0")  # type: ignore[assignment]
    assert fake.sent == [
        {
            "arbitration_id": 0x123,
            "data": b"\xde\xad\xbe\xef",
            "is_extended_id": True,
            "is_fd": True,
            "bitrate_switch": True,
        }
    ]


def test_can_send_is_gated(
    registry: BusRegistry, closed_gate: WriteGate
) -> None:
    with pytest.raises(PermissionError, match="can"):
        tools.can_send(registry, closed_gate, "can_can0", 0x123, "ff")


def test_can_receive_returns_driver_frames(registry: BusRegistry) -> None:
    fake: _FakeCan = registry.open("can_can0")  # type: ignore[assignment]
    fake.queued = [
        {
            "arbitration_id": 0x100,
            "data": "01",
            "is_extended_id": False,
            "is_fd": False,
            "bitrate_switch": False,
            "timestamp": 0.0,
        }
    ]
    out = tools.can_receive(registry, "can_can0", count=10, timeout_s=0.01)
    assert out[0]["arbitration_id"] == 0x100


def test_can_receive_forwards_filter_args(registry: BusRegistry) -> None:
    fake: _FakeCan = registry.open("can_can0")  # type: ignore[assignment]
    tools.can_receive(
        registry,
        "can_can0",
        count=1,
        timeout_s=0.01,
        can_id_filter=0x300,
        mask=0x7F0,
        extended=False,
    )
    assert fake.filters == [{"can_id": 0x300, "can_mask": 0x7F0, "extended": False}]


# ---------------------------------------------------------------------------
# Serial
# ---------------------------------------------------------------------------


def test_serial_configure_merges_kwargs(registry: BusRegistry) -> None:
    tools.serial_configure(registry, "serial_ttyUSB0", baudrate=9600, parity="E")
    tools.serial_configure(registry, "serial_ttyUSB0", stopbits=2)
    assert registry.get_config("serial_ttyUSB0") == {
        "baudrate": 9600,
        "parity": "E",
        "stopbits": 2.0,
    }


def test_serial_send_writes_decoded_hex(
    registry: BusRegistry, open_gate: WriteGate
) -> None:
    result = tools.serial_send(registry, open_gate, "serial_ttyUSB0", "48656c6c6f")
    assert result == {"sent_bytes": 5, "bus_id": "serial_ttyUSB0"}
    fake: _FakeSerial = registry.open("serial_ttyUSB0")  # type: ignore[assignment]
    assert bytes(fake.written) == b"Hello"


def test_serial_send_is_gated(
    registry: BusRegistry, closed_gate: WriteGate
) -> None:
    with pytest.raises(PermissionError, match="serial"):
        tools.serial_send(registry, closed_gate, "serial_ttyUSB0", "ff")


def test_serial_receive_returns_hex(registry: BusRegistry) -> None:
    fake: _FakeSerial = registry.open("serial_ttyUSB0")  # type: ignore[assignment]
    fake.buffered.extend(b"\x01\x02\x03")
    out = tools.serial_receive(registry, "serial_ttyUSB0", max_bytes=10)
    assert out == {"data_hex": "010203", "bytes": 3}


# ---------------------------------------------------------------------------
# I2C
# ---------------------------------------------------------------------------


def test_i2c_read_returns_driver_bytes(registry: BusRegistry) -> None:
    fake: _FakeI2c = registry.open("i2c_i2c-1")  # type: ignore[assignment]
    fake.next_read = b"\xab\xcd"
    out = tools.i2c_read(registry, "i2c_i2c-1", 0x40, 0x00, 2)
    assert out == {"data_hex": "abcd", "bytes": 2}


def test_i2c_write_is_gated(
    registry: BusRegistry, closed_gate: WriteGate
) -> None:
    with pytest.raises(PermissionError, match="i2c"):
        tools.i2c_write(registry, closed_gate, "i2c_i2c-1", 0x40, 0x00, "ff")


def test_i2c_write_forwards_to_driver(
    registry: BusRegistry, open_gate: WriteGate
) -> None:
    tools.i2c_write(registry, open_gate, "i2c_i2c-1", 0x40, 0x10, "deadbeef")
    fake: _FakeI2c = registry.open("i2c_i2c-1")  # type: ignore[assignment]
    assert fake.writes == [(0x40, 0x10, b"\xde\xad\xbe\xef")]


def test_i2c_scan_returns_only_acking_addresses(
    registry: BusRegistry, open_gate: WriteGate
) -> None:
    fake: _FakeI2c = registry.open("i2c_i2c-1")  # type: ignore[assignment]
    fake.acks = {0x40, 0x68}
    out = tools.i2c_scan(registry, open_gate, "i2c_i2c-1", start=0x30, end=0x70)
    assert out == {"bus_id": "i2c_i2c-1", "found": [0x40, 0x68], "range": [0x30, 0x70]}


def test_i2c_scan_is_gated(
    registry: BusRegistry, closed_gate: WriteGate
) -> None:
    with pytest.raises(PermissionError, match="i2c"):
        tools.i2c_scan(registry, closed_gate, "i2c_i2c-1")


# ---------------------------------------------------------------------------
# SPI
# ---------------------------------------------------------------------------


def test_spi_configure_stores_kwargs(registry: BusRegistry) -> None:
    out = tools.spi_configure(
        registry, "spi_spidev0.0", max_speed_hz=4_000_000, mode=3
    )
    assert out["config"] == {"max_speed_hz": 4_000_000, "mode": 3}


def test_spi_xfer_returns_rx_hex(
    registry: BusRegistry, open_gate: WriteGate
) -> None:
    fake: _FakeSpi = registry.open("spi_spidev0.0")  # type: ignore[assignment]
    fake.next_rx = b"\x55\xaa"
    out = tools.spi_xfer(registry, open_gate, "spi_spidev0.0", "0102")
    assert out == {"rx_hex": "55aa", "bytes": 2}
    assert fake.last_tx == b"\x01\x02"


def test_spi_xfer_per_call_speed_override(
    registry: BusRegistry, open_gate: WriteGate
) -> None:
    fake: _FakeSpi = registry.open("spi_spidev0.0")  # type: ignore[assignment]
    tools.spi_xfer(registry, open_gate, "spi_spidev0.0", "00", speed_hz=250_000)
    assert fake.last_speed_hz == 250_000


def test_spi_xfer_is_gated(
    registry: BusRegistry, closed_gate: WriteGate
) -> None:
    with pytest.raises(PermissionError, match="spi"):
        tools.spi_xfer(registry, closed_gate, "spi_spidev0.0", "00")


# ---------------------------------------------------------------------------
# GPIO
# ---------------------------------------------------------------------------


def test_gpio_configure_forwards_every_kwarg(registry: BusRegistry) -> None:
    out = tools.gpio_configure(
        registry,
        "gpio_gpiochip0",
        17,
        "out",
        pull="up",
        active_low=True,
        debounce_us=2_000,
    )
    assert out == {
        "pin": 17,
        "direction": "out",
        "pull": "up",
        "active_low": True,
        "debounce_us": 2_000,
    }
    fake: _FakeGpio = registry.open("gpio_gpiochip0")  # type: ignore[assignment]
    assert fake.configured == [
        {
            "pin": 17,
            "direction": "out",
            "pull": "up",
            "active_low": True,
            "debounce_us": 2_000,
        }
    ]


def test_gpio_read_returns_value(registry: BusRegistry) -> None:
    fake: _FakeGpio = registry.open("gpio_gpiochip0")  # type: ignore[assignment]
    fake.pin_values[17] = 1
    out = tools.gpio_read(registry, "gpio_gpiochip0", 17)
    assert out == {"pin": 17, "value": 1}


def test_gpio_write_is_gated(
    registry: BusRegistry, closed_gate: WriteGate
) -> None:
    with pytest.raises(PermissionError, match="gpio"):
        tools.gpio_write(registry, closed_gate, "gpio_gpiochip0", 17, 1)


def test_gpio_write_forwards_to_driver(
    registry: BusRegistry, open_gate: WriteGate
) -> None:
    tools.gpio_write(registry, open_gate, "gpio_gpiochip0", 17, 1)
    fake: _FakeGpio = registry.open("gpio_gpiochip0")  # type: ignore[assignment]
    assert fake.writes == [(17, 1)]
