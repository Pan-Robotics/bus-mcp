"""GPIO driver — wraps ``lgpio`` (works on Pi 4 / Pi 5 / CM4 / CM5).

``RPi.GPIO`` is deliberately avoided: it's BCM2835-only and was
deprecated on the Pi 5 in favour of lgpio's gpiochip API.
"""

from __future__ import annotations


class GpioBus:
    def __init__(self, path: str) -> None:
        import lgpio  # deferred

        # /dev/gpiochip0 → chip 0
        chip_num = int(path.removeprefix("/dev/gpiochip"))
        self._lgpio = lgpio
        self._h = lgpio.gpiochip_open(chip_num)
        self._claimed_inputs: set[int] = set()
        self._claimed_outputs: set[int] = set()
        self.path = path
        self.config = {"path": path}

    def configure(
        self,
        pin: int,
        *,
        direction: str,
        pull: str = "none",
        active_low: bool = False,
        debounce_us: int = 0,
    ) -> None:
        lgpio = self._lgpio
        # Pull mode + active-low both ride in the lgpio "flags" int.
        if pull == "up":
            flags = lgpio.SET_PULL_UP
        elif pull == "down":
            flags = lgpio.SET_PULL_DOWN
        elif pull == "none":
            flags = lgpio.SET_PULL_NONE
        else:
            raise ValueError(f"unknown pull: {pull!r} — expected none/up/down")
        if active_low:
            flags |= lgpio.SET_ACTIVE_LOW

        if direction == "in":
            lgpio.gpio_claim_input(self._h, int(pin), flags)
            if debounce_us > 0:
                # lgpio takes debounce in microseconds.
                lgpio.gpio_set_debounce_micros(self._h, int(pin), int(debounce_us))
            self._claimed_inputs.add(int(pin))
            self._claimed_outputs.discard(int(pin))
        elif direction == "out":
            lgpio.gpio_claim_output(self._h, int(pin), 0, flags)
            self._claimed_outputs.add(int(pin))
            self._claimed_inputs.discard(int(pin))
        else:
            raise ValueError(f"unknown direction: {direction!r} — expected in/out")

    def read(self, pin: int) -> int:
        lgpio = self._lgpio
        pin_i = int(pin)
        if pin_i not in self._claimed_inputs and pin_i not in self._claimed_outputs:
            lgpio.gpio_claim_input(self._h, pin_i)
            self._claimed_inputs.add(pin_i)
        return int(lgpio.gpio_read(self._h, pin_i))

    def write(self, pin: int, value: int) -> None:
        lgpio = self._lgpio
        pin_i = int(pin)
        if pin_i not in self._claimed_outputs:
            lgpio.gpio_claim_output(self._h, pin_i, 0)
            self._claimed_outputs.add(pin_i)
            self._claimed_inputs.discard(pin_i)
        lgpio.gpio_write(self._h, pin_i, 1 if value else 0)

    def close(self) -> None:
        try:
            self._lgpio.gpiochip_close(self._h)
        except Exception:
            pass
