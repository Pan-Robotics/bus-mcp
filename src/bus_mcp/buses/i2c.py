"""I2C driver — wraps ``smbus2``.

Bus-wide config is intentionally minimal — clock-stretching and force
flags are device-tree concerns on the Pi. Per-call ``read`` /
``write_byte`` / ``read_word`` shapes are surfaced through the tool
layer.
"""

from __future__ import annotations


class I2cBus:
    def __init__(self, path: str, *, force: bool = False) -> None:
        import smbus2  # deferred

        # /dev/i2c-1 → bus number 1
        bus_num = int(path.rsplit("-", 1)[-1])
        self._bus = smbus2.SMBus(bus_num, force=bool(force))
        self.path = path
        self.config = {"path": path, "force": bool(force)}

    def read(self, address: int, register: int, length: int) -> bytes:
        if length <= 0:
            return b""
        data = self._bus.read_i2c_block_data(int(address), int(register), int(length))
        return bytes(data)

    def write(self, address: int, register: int, data: bytes) -> None:
        self._bus.write_i2c_block_data(int(address), int(register), list(data))

    def write_quick(self, address: int) -> None:
        """Bus probe — sends an address + write bit, no data. Use this to
        scan which 7-bit addresses ACK."""
        self._bus.write_quick(int(address))

    def close(self) -> None:
        try:
            self._bus.close()
        except Exception:
            pass
