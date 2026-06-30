"""UART + RS485 driver — wraps ``pyserial``.

All ``pyserial`` knobs the agent might want to tune mid-session
(baudrate, framing, flow control) are first-class constructor kwargs so
the ``serial_configure`` tool can pass them straight through.
"""

from __future__ import annotations


_PARITY_MAP = {
    "N": "N",
    "E": "E",
    "O": "O",
    "M": "M",  # mark
    "S": "S",  # space
    "NONE": "N",
    "EVEN": "E",
    "ODD": "O",
}


class SerialBus:
    def __init__(
        self,
        path: str,
        *,
        baudrate: int = 115_200,
        bytesize: int = 8,
        parity: str = "N",
        stopbits: float = 1,
        timeout_s: float = 0.5,
        rtscts: bool = False,
        dsrdtr: bool = False,
        xonxoff: bool = False,
    ) -> None:
        import serial  # deferred

        parity_norm = _PARITY_MAP.get(str(parity).upper())
        if parity_norm is None:
            raise ValueError(
                f"unknown parity: {parity!r} — expected one of N/E/O/M/S"
            )
        if bytesize not in (5, 6, 7, 8):
            raise ValueError(f"bytesize must be 5/6/7/8, got {bytesize!r}")
        if stopbits not in (1, 1.5, 2):
            raise ValueError(f"stopbits must be 1/1.5/2, got {stopbits!r}")

        self._port = serial.Serial(
            port=path,
            baudrate=int(baudrate),
            bytesize=int(bytesize),
            parity=parity_norm,
            stopbits=float(stopbits),
            timeout=float(timeout_s),
            rtscts=bool(rtscts),
            dsrdtr=bool(dsrdtr),
            xonxoff=bool(xonxoff),
        )
        self.path = path
        self.config = {
            "path": path,
            "baudrate": int(baudrate),
            "bytesize": int(bytesize),
            "parity": parity_norm,
            "stopbits": float(stopbits),
            "timeout_s": float(timeout_s),
            "rtscts": bool(rtscts),
            "dsrdtr": bool(dsrdtr),
            "xonxoff": bool(xonxoff),
        }

    def write(self, data: bytes) -> int:
        return int(self._port.write(data) or 0)

    def read(self, *, max_bytes: int = 1024, timeout_s: float | None = None) -> bytes:
        if timeout_s is not None:
            self._port.timeout = float(timeout_s)
        return bytes(self._port.read(int(max_bytes)))

    def close(self) -> None:
        try:
            self._port.close()
        except Exception:
            pass
