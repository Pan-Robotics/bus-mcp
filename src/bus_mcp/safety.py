"""Write-permission gate.

The default config is read-only on every bus. The operator opts in to
writes per-bus (``--allow-write=can,serial``) or to all buses
(``--allow-write``). The gate refuses every write attempt cleanly so the
agent can surface the state to the user instead of dropping to a stack
trace.
"""

from __future__ import annotations

from collections.abc import Iterable

BUSES: tuple[str, ...] = ("can", "serial", "i2c", "spi", "gpio")


class WriteGate:
    """Tracks which bus kinds the operator has unlocked for writes."""

    def __init__(self, allowed: Iterable[str]) -> None:
        allowed_set = {k.strip().lower() for k in allowed if k.strip()}
        bad = sorted(k for k in allowed_set if k not in BUSES)
        if bad:
            raise ValueError(
                f"unknown bus kind(s): {bad!r} — valid kinds are {list(BUSES)!r}"
            )
        self._allowed = frozenset(allowed_set)

    def check(self, kind: str) -> None:
        """Raise ``PermissionError`` unless ``kind`` is unlocked."""
        if kind not in self._allowed:
            raise PermissionError(
                f"writes to {kind} buses are disabled. "
                f"Re-launch bus-mcp with --allow-write or --allow-write={kind}."
            )

    @property
    def allowed(self) -> frozenset[str]:
        return self._allowed


def parse_allow_write(raw: str | None) -> set[str]:
    """Parse the CLI flag into a set of bus kinds.

    - ``None``  → empty set (read-only)
    - ``"*"``   → every kind (CLI passes this when ``--allow-write`` is
                  used with no argument)
    - ``"can,serial"`` → ``{"can", "serial"}``
    """
    if raw is None:
        return set()
    if raw == "*":
        return set(BUSES)
    out: set[str] = set()
    for part in raw.split(","):
        cleaned = part.strip().lower()
        if cleaned:
            out.add(cleaned)
    return out
