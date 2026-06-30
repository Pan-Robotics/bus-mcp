import pytest

import bus_mcp.discovery as discovery


def _stub_globs(monkeypatch: pytest.MonkeyPatch, mapping: dict[str, list[str]]) -> None:
    monkeypatch.setattr(
        discovery.glob,
        "glob",
        lambda pat: mapping.get(pat, []),
    )


# ---------------------------------------------------------------------------
# Per-kind probes
# ---------------------------------------------------------------------------


def test_can_probe_keeps_socketcan_ifaces_drops_vcan_and_unrelated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(discovery, "_safe_listdir", lambda p: ["can0", "vcan0", "eth0", "lo"])
    _stub_globs(monkeypatch, {})
    out = discovery._discover_can()
    ids = [b.bus_id for b in out]
    assert ids == ["can_can0"]
    assert out[0].device == "can0"
    assert out[0].kind == "can"


def test_can_probe_picks_up_vendor_char_devs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(discovery, "_safe_listdir", lambda p: [])
    _stub_globs(monkeypatch, {"/dev/can*": ["/dev/can0", "/dev/can1"]})
    ids = [b.bus_id for b in discovery._discover_can()]
    assert ids == ["can_can0", "can_can1"]


def test_serial_probe_covers_every_common_path(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_globs(
        monkeypatch,
        {
            "/dev/ttyUSB*": ["/dev/ttyUSB0", "/dev/ttyUSB1"],
            "/dev/ttyACM*": ["/dev/ttyACM0"],
            "/dev/ttyAMA*": ["/dev/ttyAMA0"],
            "/dev/ttyS*": [],
        },
    )
    ids = [b.bus_id for b in discovery._discover_serial()]
    assert ids == [
        "serial_ttyUSB0",
        "serial_ttyUSB1",
        "serial_ttyACM0",
        "serial_ttyAMA0",
    ]


def test_i2c_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_globs(monkeypatch, {"/dev/i2c-*": ["/dev/i2c-1", "/dev/i2c-3"]})
    out = discovery._discover_i2c()
    assert [b.bus_id for b in out] == ["i2c_i2c-1", "i2c_i2c-3"]
    assert out[0].kind == "i2c"
    assert out[0].device == "/dev/i2c-1"


def test_spi_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_globs(monkeypatch, {"/dev/spidev*": ["/dev/spidev0.0", "/dev/spidev0.1"]})
    ids = [b.bus_id for b in discovery._discover_spi()]
    assert ids == ["spi_spidev0.0", "spi_spidev0.1"]


def test_gpio_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_globs(
        monkeypatch,
        {"/dev/gpiochip*": ["/dev/gpiochip0", "/dev/gpiochip4"]},
    )
    out = discovery._discover_gpio()
    ids = [b.bus_id for b in out]
    assert ids == ["gpio_gpiochip0", "gpio_gpiochip4"]


# ---------------------------------------------------------------------------
# Aggregate
# ---------------------------------------------------------------------------


def test_discover_buses_returns_sorted_union(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(discovery, "_safe_listdir", lambda p: ["can0"])
    _stub_globs(
        monkeypatch,
        {
            "/dev/can*": [],
            "/dev/ttyUSB*": ["/dev/ttyUSB0"],
            "/dev/ttyACM*": [],
            "/dev/ttyAMA*": [],
            "/dev/ttyS*": [],
            "/dev/i2c-*": ["/dev/i2c-1"],
            "/dev/spidev*": [],
            "/dev/gpiochip*": ["/dev/gpiochip0"],
        },
    )
    out = discovery.discover_buses()
    ids = [b.bus_id for b in out]
    assert ids == sorted(ids)
    assert set(ids) == {"can_can0", "serial_ttyUSB0", "i2c_i2c-1", "gpio_gpiochip0"}


def test_discover_returns_empty_list_on_bare_linux(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(discovery, "_safe_listdir", lambda p: [])
    _stub_globs(monkeypatch, {})
    assert discovery.discover_buses() == []
