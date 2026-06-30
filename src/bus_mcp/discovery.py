"""Probe ``/dev/*`` + ``/sys/class/net`` for buses we can expose.

The probe is glob-based and pure-stdlib — no bus libraries imported. It
runs on any Linux box, but only a Raspberry Pi will surface the
interesting set (SocketCAN, GPIO chips, the SPI/I2C overlays).
"""

from __future__ import annotations

import glob
import os
from pathlib import Path

from .registry import DiscoveredBus


def discover_buses() -> list[DiscoveredBus]:
    """Run every probe and return the union, sorted by ``bus_id``."""
    out: list[DiscoveredBus] = []
    out.extend(_discover_can())
    out.extend(_discover_serial())
    out.extend(_discover_i2c())
    out.extend(_discover_spi())
    out.extend(_discover_gpio())
    return sorted(out, key=lambda b: b.bus_id)


# ---------------------------------------------------------------------------
# Per-kind probes — kept module-private but exposed for tests.
# ---------------------------------------------------------------------------


def _discover_can() -> list[DiscoveredBus]:
    """SocketCAN interfaces (``can0`` etc.) plus any vendor ``/dev/can*``."""
    out: list[DiscoveredBus] = []
    for name in sorted(_safe_listdir("/sys/class/net")):
        # match `can[0-9]+` exactly — keep out vcanN (virtual CAN you'd
        # bring up for testing) and unrelated `canberra`-style names.
        if name.startswith("can") and name[3:].isdigit():
            out.append(DiscoveredBus(bus_id=f"can_{name}", kind="can", device=name))
    for path in sorted(glob.glob("/dev/can*")):
        out.append(
            DiscoveredBus(bus_id=f"can_{Path(path).name}", kind="can", device=path)
        )
    return out


def _discover_serial() -> list[DiscoveredBus]:
    """UART / RS485 ports. ``ttyAMA0`` / ``ttyS0`` are the Pi's on-board
    UARTs; USB serial adapters land at ``ttyUSB*`` / ``ttyACM*``."""
    out: list[DiscoveredBus] = []
    patterns = ("/dev/ttyUSB*", "/dev/ttyACM*", "/dev/ttyAMA*", "/dev/ttyS*")
    for pat in patterns:
        for path in sorted(glob.glob(pat)):
            out.append(
                DiscoveredBus(
                    bus_id=f"serial_{Path(path).name}",
                    kind="serial",
                    device=path,
                )
            )
    return out


def _discover_i2c() -> list[DiscoveredBus]:
    out: list[DiscoveredBus] = []
    for path in sorted(glob.glob("/dev/i2c-*")):
        out.append(
            DiscoveredBus(bus_id=f"i2c_{Path(path).name}", kind="i2c", device=path)
        )
    return out


def _discover_spi() -> list[DiscoveredBus]:
    out: list[DiscoveredBus] = []
    for path in sorted(glob.glob("/dev/spidev*")):
        out.append(
            DiscoveredBus(bus_id=f"spi_{Path(path).name}", kind="spi", device=path)
        )
    return out


def _discover_gpio() -> list[DiscoveredBus]:
    """One logical bus per ``gpiochip``. A Pi 5 has several — we expose
    them all and let the agent target the right one by ``bus_id``."""
    out: list[DiscoveredBus] = []
    for path in sorted(glob.glob("/dev/gpiochip*")):
        out.append(
            DiscoveredBus(bus_id=f"gpio_{Path(path).name}", kind="gpio", device=path)
        )
    return out


def _safe_listdir(path: str) -> list[str]:
    try:
        return os.listdir(path)
    except OSError:
        return []
