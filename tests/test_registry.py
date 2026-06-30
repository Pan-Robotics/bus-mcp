from typing import Any

import pytest

from bus_mcp.registry import BusRegistry, DiscoveredBus


# ---------------------------------------------------------------------------
# Test doubles — one fake per kind. Factory is ``(device, config)``.
# ---------------------------------------------------------------------------


class _FakeBus:
    """Records open args + tracks close so test_close_all_closes_every_bus
    can verify the registry tore everything down cleanly."""

    def __init__(self, device: str, **config: Any) -> None:
        self.device = device
        self.config = config
        self.closed = False

    def close(self) -> None:
        self.closed = True


def _fake_factories() -> dict[str, Any]:
    def make(device: str, config: dict[str, Any]) -> _FakeBus:
        return _FakeBus(device, **config)

    return {k: make for k in ("can", "serial", "i2c", "spi", "gpio")}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_fresh_registry_is_empty() -> None:
    r = BusRegistry(factories=_fake_factories())
    assert r.list() == []


def test_register_then_list_returns_sorted_descriptors() -> None:
    r = BusRegistry(factories=_fake_factories())
    r.register(DiscoveredBus("serial_ttyUSB0", "serial", "/dev/ttyUSB0"))
    r.register(DiscoveredBus("can_can0", "can", "can0"))
    assert [b.bus_id for b in r.list()] == ["can_can0", "serial_ttyUSB0"]


def test_register_rejects_duplicate_bus_id() -> None:
    r = BusRegistry(factories=_fake_factories())
    r.register(DiscoveredBus("can_can0", "can", "can0"))
    with pytest.raises(ValueError, match="duplicate"):
        r.register(DiscoveredBus("can_can0", "can", "can0"))


def test_register_rejects_unknown_kind() -> None:
    r = BusRegistry(factories=_fake_factories())
    with pytest.raises(ValueError, match="unknown bus kind"):
        r.register(DiscoveredBus("zigbee_0", "zigbee", "/dev/zigbee0"))


def test_get_raises_keyerror_for_unknown_id() -> None:
    r = BusRegistry(factories=_fake_factories())
    with pytest.raises(KeyError, match="unknown bus_id"):
        r.get("ghost")


def test_open_invokes_factory_with_device_and_config() -> None:
    seen: list[tuple[str, dict[str, Any]]] = []

    def factory(dev: str, config: dict[str, Any]) -> _FakeBus:
        seen.append((dev, dict(config)))
        return _FakeBus(dev, **config)

    r = BusRegistry(factories={k: factory for k in ("can", "serial", "i2c", "spi", "gpio")})
    r.register(DiscoveredBus("can_can0", "can", "can0"))
    r.set_config("can_can0", {"bitrate": 250_000})
    inst = r.open("can_can0")
    assert isinstance(inst, _FakeBus)
    assert seen == [("can0", {"bitrate": 250_000})]


def test_open_caches_so_repeat_calls_reuse_the_same_instance() -> None:
    r = BusRegistry(factories=_fake_factories())
    r.register(DiscoveredBus("can_can0", "can", "can0"))
    a = r.open("can_can0")
    b = r.open("can_can0")
    assert a is b


def test_set_config_merges_and_closes_open_bus() -> None:
    r = BusRegistry(factories=_fake_factories())
    r.register(DiscoveredBus("can_can0", "can", "can0"))
    inst1 = r.open("can_can0")
    r.set_config("can_can0", {"bitrate": 1_000_000})
    assert inst1.closed is True
    # Next open builds a fresh instance with the new config.
    inst2 = r.open("can_can0")
    assert inst2 is not inst1
    assert inst2.config == {"bitrate": 1_000_000}


def test_set_config_preserves_previous_fields() -> None:
    r = BusRegistry(factories=_fake_factories())
    r.register(DiscoveredBus("serial_ttyUSB0", "serial", "/dev/ttyUSB0"))
    r.set_config("serial_ttyUSB0", {"baudrate": 9600, "parity": "E"})
    r.set_config("serial_ttyUSB0", {"baudrate": 115_200})
    cfg = r.get_config("serial_ttyUSB0")
    assert cfg == {"baudrate": 115_200, "parity": "E"}


def test_set_config_rejects_unknown_bus_id() -> None:
    r = BusRegistry(factories=_fake_factories())
    with pytest.raises(KeyError, match="unknown bus_id"):
        r.set_config("ghost", {"bitrate": 500_000})


def test_close_releases_one_bus() -> None:
    r = BusRegistry(factories=_fake_factories())
    r.register(DiscoveredBus("can_can0", "can", "can0"))
    r.register(DiscoveredBus("can_can1", "can", "can1"))
    a = r.open("can_can0")
    b = r.open("can_can1")
    assert r.close("can_can0") is True
    assert a.closed is True
    # The other bus is untouched.
    assert b.closed is False
    # Closing an already-closed bus returns False (idempotent).
    assert r.close("can_can0") is False


def test_close_all_closes_every_opened_bus() -> None:
    r = BusRegistry(factories=_fake_factories())
    r.register(DiscoveredBus("can_can0", "can", "can0"))
    r.register(DiscoveredBus("serial_ttyUSB0", "serial", "/dev/ttyUSB0"))
    inst_a = r.open("can_can0")
    inst_b = r.open("serial_ttyUSB0")
    r.close_all()
    assert inst_a.closed is True
    assert inst_b.closed is True
    # After close_all, the next open() must mint a fresh instance.
    inst_c = r.open("can_can0")
    assert inst_c is not inst_a


def test_close_all_tolerates_misbehaving_close() -> None:
    class _BadClose:
        def __init__(self, device: str, **_: Any) -> None:
            self.device = device

        def close(self) -> None:
            raise RuntimeError("boom")

    def bad_factory(dev: str, config: dict[str, Any]) -> _BadClose:
        return _BadClose(dev, **config)

    def good_factory(dev: str, config: dict[str, Any]) -> _FakeBus:
        return _FakeBus(dev, **config)

    r = BusRegistry(
        factories={
            "can": bad_factory,
            "serial": good_factory,
            "i2c": good_factory,
            "spi": good_factory,
            "gpio": good_factory,
        }
    )
    r.register(DiscoveredBus("can_can0", "can", "can0"))
    r.register(DiscoveredBus("serial_ttyUSB0", "serial", "/dev/ttyUSB0"))
    good = r.open("serial_ttyUSB0")
    r.open("can_can0")
    r.close_all()  # must not raise
    assert good.closed is True
