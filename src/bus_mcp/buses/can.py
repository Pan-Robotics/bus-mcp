"""SocketCAN driver — wraps ``python-can``.

Every constructor arg maps to a tool kwarg the agent can pass via
``can_configure``. Defaults are conservative for hobbyist use (classic
CAN at 500 kbit/s with no auto-restart).
"""

from __future__ import annotations

from typing import Any


class CanBus:
    def __init__(
        self,
        channel: str,
        *,
        bitrate: int = 500_000,
        fd: bool = False,
        data_bitrate: int | None = None,
        restart_ms: int = 0,
        receive_own_messages: bool = False,
    ) -> None:
        import can  # deferred — only needed when a CAN tool is called

        kwargs: dict[str, Any] = {
            "channel": channel,
            "interface": "socketcan",
            "bitrate": int(bitrate),
            "fd": bool(fd),
            "receive_own_messages": bool(receive_own_messages),
        }
        if fd and data_bitrate is not None:
            kwargs["data_bitrate"] = int(data_bitrate)
        if restart_ms:
            # python-can hands this to the kernel via ``ip link``; not all
            # backends honour it, but socketcan does.
            kwargs["restart_ms"] = int(restart_ms)

        self._can = can
        self._bus = can.interface.Bus(**kwargs)
        self.channel = channel
        # Echo back the active config so the configure tool can return it.
        self.config = {
            "channel": channel,
            "bitrate": int(bitrate),
            "fd": bool(fd),
            "data_bitrate": int(data_bitrate) if (fd and data_bitrate) else None,
            "restart_ms": int(restart_ms),
            "receive_own_messages": bool(receive_own_messages),
        }

    def send(
        self,
        arbitration_id: int,
        data: bytes,
        *,
        is_extended_id: bool = False,
        is_fd: bool = False,
        bitrate_switch: bool = False,
    ) -> None:
        msg = self._can.Message(
            arbitration_id=int(arbitration_id),
            data=data,
            is_extended_id=bool(is_extended_id),
            is_fd=bool(is_fd),
            bitrate_switch=bool(bitrate_switch),
        )
        self._bus.send(msg)

    def receive(
        self,
        *,
        timeout_s: float = 1.0,
        count: int = 10,
        can_id_filter: int | None = None,
        mask: int | None = None,
        extended: bool = False,
    ) -> list[dict[str, Any]]:
        """Drain up to ``count`` frames or stop on the first timeout.

        Optional single-filter convenience: pass ``can_id_filter`` (and
        optionally ``mask``) to push a SocketCAN filter to the kernel so
        unmatched frames never wake userspace.
        """
        if can_id_filter is not None:
            self._bus.set_filters(
                [
                    {
                        "can_id": int(can_id_filter),
                        "can_mask": int(mask) if mask is not None else 0x7FF,
                        "extended": bool(extended),
                    }
                ]
            )
        try:
            frames: list[dict[str, Any]] = []
            for _ in range(max(1, count)):
                msg = self._bus.recv(timeout=timeout_s)
                if msg is None:
                    break
                frames.append(
                    {
                        "arbitration_id": int(msg.arbitration_id),
                        "data": bytes(msg.data).hex(),
                        "is_extended_id": bool(msg.is_extended_id),
                        "is_fd": bool(msg.is_fd),
                        "bitrate_switch": bool(msg.bitrate_switch),
                        "timestamp": float(msg.timestamp),
                    }
                )
            return frames
        finally:
            if can_id_filter is not None:
                # Clear the filter so the next receive() sees everything.
                self._bus.set_filters(None)

    def close(self) -> None:
        try:
            self._bus.shutdown()
        except Exception:
            pass
