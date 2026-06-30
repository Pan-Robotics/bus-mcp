import pytest

from bus_mcp.safety import BUSES, WriteGate, parse_allow_write


# ---------------------------------------------------------------------------
# parse_allow_write
# ---------------------------------------------------------------------------


def test_parse_none_is_empty_set() -> None:
    assert parse_allow_write(None) == set()


def test_parse_star_unlocks_every_bus() -> None:
    assert parse_allow_write("*") == set(BUSES)


def test_parse_comma_separated_list() -> None:
    assert parse_allow_write("can,serial") == {"can", "serial"}


def test_parse_trims_whitespace_and_lowercases() -> None:
    assert parse_allow_write(" CAN , Spi ") == {"can", "spi"}


def test_parse_empty_string_yields_empty_set() -> None:
    assert parse_allow_write("") == set()


# ---------------------------------------------------------------------------
# WriteGate
# ---------------------------------------------------------------------------


def test_default_gate_refuses_every_write_kind() -> None:
    gate = WriteGate(set())
    for kind in BUSES:
        with pytest.raises(PermissionError, match="--allow-write"):
            gate.check(kind)


def test_gate_allows_unlocked_kinds_only() -> None:
    gate = WriteGate({"can"})
    gate.check("can")  # must not raise
    with pytest.raises(PermissionError):
        gate.check("serial")


def test_gate_error_message_names_the_specific_bus_kind() -> None:
    gate = WriteGate(set())
    with pytest.raises(PermissionError, match="i2c"):
        gate.check("i2c")


def test_gate_rejects_unknown_bus_kind_at_construction() -> None:
    with pytest.raises(ValueError, match="unknown bus kind"):
        WriteGate({"bluetooth"})


def test_gate_allowed_is_readonly_frozenset() -> None:
    gate = WriteGate({"can", "spi"})
    assert gate.allowed == frozenset({"can", "spi"})
    assert isinstance(gate.allowed, frozenset)
