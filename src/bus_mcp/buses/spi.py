"""SPI driver — wraps ``spidev``.

Every kwarg is per-bus default; ``xfer`` accepts a per-transfer
``speed_hz`` override since some peripherals want different speeds for
config vs. data registers.
"""

from __future__ import annotations


class SpiBus:
    def __init__(
        self,
        path: str,
        *,
        max_speed_hz: int = 1_000_000,
        mode: int = 0,
        bits_per_word: int = 8,
        lsb_first: bool = False,
        cs_high: bool = False,
    ) -> None:
        import spidev  # deferred

        if mode not in (0, 1, 2, 3):
            raise ValueError(f"SPI mode must be 0/1/2/3, got {mode!r}")
        # /dev/spidev0.1 → bus=0, device=1
        head = path.removeprefix("/dev/spidev")
        bus_str, device_str = head.split(".", 1)
        self._spi = spidev.SpiDev()
        self._spi.open(int(bus_str), int(device_str))
        self._spi.max_speed_hz = int(max_speed_hz)
        self._spi.mode = int(mode)
        self._spi.bits_per_word = int(bits_per_word)
        self._spi.lsbfirst = bool(lsb_first)
        self._spi.cshigh = bool(cs_high)
        self.path = path
        self.config = {
            "path": path,
            "max_speed_hz": int(max_speed_hz),
            "mode": int(mode),
            "bits_per_word": int(bits_per_word),
            "lsb_first": bool(lsb_first),
            "cs_high": bool(cs_high),
        }

    def xfer(self, tx: bytes, *, speed_hz: int | None = None) -> bytes:
        if speed_hz is not None:
            rx = self._spi.xfer2(list(tx), int(speed_hz))
        else:
            rx = self._spi.xfer2(list(tx))
        return bytes(rx)

    def close(self) -> None:
        try:
            self._spi.close()
        except Exception:
            pass
