"""In-memory map of ``bus_id`` → bus driver instance.

The registry is split into two phases so the CLI can run ``bus-mcp list``
on a dev laptop without `python-can` / `lgpio` / etc. installed:

  1. *Discovery* populates :class:`DiscoveredBus` descriptors (cheap,
     pure-stdlib — see :mod:`bus_mcp.discovery`).
  2. *Open* instantiates the actual driver on demand via factories that
     do the heavy imports lazily. Tests inject fake factories so they
     never touch real hardware.

Per-bus config (CAN bitrate, serial baud, SPI mode, …) is stashed
separately so the agent can call ``can_configure(bus_id, bitrate=…)``
mid-session — the next ``open()`` uses the new config.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

# Factory signature — given the device path / channel and a kwargs
# dict, return an object with a ``close()`` method. The MCP tool layer
# asserts the remaining bus-specific methods exist at call time.
BusFactory = Callable[[str, dict[str, Any]], Any]


@dataclass(frozen=True)
class DiscoveredBus:
    """A bus the discovery scan found on this host."""

    bus_id: str  # stable identifier the agent uses to address the bus
    kind: str  # "can" | "serial" | "i2c" | "spi" | "gpio"
    device: str  # /dev path, SocketCAN iface name, or gpiochip path


def _default_factories() -> dict[str, BusFactory]:
    """Build the production factory map with deferred bus-lib imports."""

    def make_can(device: str, config: dict[str, Any]) -> Any:
        from .buses.can import CanBus

        return CanBus(device, **config)

    def make_serial(device: str, config: dict[str, Any]) -> Any:
        from .buses.serial import SerialBus

        return SerialBus(device, **config)

    def make_i2c(device: str, config: dict[str, Any]) -> Any:
        from .buses.i2c import I2cBus

        return I2cBus(device, **config)

    def make_spi(device: str, config: dict[str, Any]) -> Any:
        from .buses.spi import SpiBus

        return SpiBus(device, **config)

    def make_gpio(device: str, config: dict[str, Any]) -> Any:
        from .buses.gpio import GpioBus

        return GpioBus(device, **config)

    return {
        "can": make_can,
        "serial": make_serial,
        "i2c": make_i2c,
        "spi": make_spi,
        "gpio": make_gpio,
    }


class BusRegistry:
    """Holds discovered descriptors + per-bus config + lazily-opened
    driver instances."""

    def __init__(self, factories: dict[str, BusFactory] | None = None) -> None:
        self._open: dict[str, Any] = {}
        self._discovered: dict[str, DiscoveredBus] = {}
        self._configs: dict[str, dict[str, Any]] = {}
        self._factories = factories if factories is not None else _default_factories()

    def register(self, b: DiscoveredBus) -> None:
        if b.bus_id in self._discovered:
            raise ValueError(f"duplicate bus_id: {b.bus_id!r}")
        if b.kind not in self._factories:
            raise ValueError(
                f"unknown bus kind: {b.kind!r} — registered kinds are "
                f"{sorted(self._factories)!r}"
            )
        self._discovered[b.bus_id] = b

    def list(self) -> list[DiscoveredBus]:
        return sorted(self._discovered.values(), key=lambda b: b.bus_id)

    def get(self, bus_id: str) -> DiscoveredBus:
        if bus_id not in self._discovered:
            raise KeyError(f"unknown bus_id: {bus_id!r}")
        return self._discovered[bus_id]

    def set_config(self, bus_id: str, config: dict[str, Any]) -> dict[str, Any]:
        """Update the kwargs used when the bus is next opened.

        If the bus is already open, it's closed so the next ``open()``
        rebuilds with the new config. Returns the merged config dict so
        callers can echo it back to the user.
        """
        self.get(bus_id)  # validate the id
        merged = dict(self._configs.get(bus_id, {}))
        merged.update(config)
        self._configs[bus_id] = merged
        self.close(bus_id)
        return merged

    def get_config(self, bus_id: str) -> dict[str, Any]:
        self.get(bus_id)
        return dict(self._configs.get(bus_id, {}))

    def open(self, bus_id: str) -> Any:
        """Return a cached driver instance, opening it on first call."""
        if bus_id in self._open:
            return self._open[bus_id]
        descriptor = self.get(bus_id)
        config = self._configs.get(bus_id, {})
        instance = self._factories[descriptor.kind](descriptor.device, config)
        self._open[bus_id] = instance
        return instance

    def close(self, bus_id: str) -> bool:
        """Close one open bus. Returns True if anything was closed."""
        inst = self._open.pop(bus_id, None)
        if inst is None:
            return False
        close = getattr(inst, "close", None)
        if callable(close):
            try:
                close()
            except Exception:
                pass
        return True

    def close_all(self) -> None:
        for bus_id in list(self._open):
            self.close(bus_id)
