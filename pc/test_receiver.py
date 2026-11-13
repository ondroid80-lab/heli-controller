"""Testy mapování a parsování paketů (běží na libovolném OS, bez vgamepad)."""
import json
import math

from receiver import Mapper, apply_deadzone, load_config, parse_packet, clamp


def test_deadzone():
    assert apply_deadzone(0.02, 0.05) == 0.0
    assert apply_deadzone(-0.02, 0.05) == 0.0
    assert math.isclose(apply_deadzone(1.0, 0.05), 1.0)
    assert math.isclose(apply_deadzone(-1.0, 0.05), -1.0)
    assert apply_deadzone(0.525, 0.05) > 0.5  # přepočet na plný rozsah


def test_clamp():
    assert clamp(3) == 1.0
    assert clamp(-3) == -1.0


def test_pitch_forward_maps_to_stick_forward():
    m = Mapper(load_config())
    axes = m.map({"pitch": 0.8})
    assert axes.ly < 0  # výchozí převrácení: náklon dopředu = páka dopředu (záporné Y)
    assert axes.lx == 0.0


def test_roll_and_yaw():
    m = Mapper(load_config())
    axes = m.map({"roll": -0.5, "yaw": 0.6})
    assert axes.lx < 0
    assert axes.rx > 0


def test_collective_split_to_triggers():
    m = Mapper(load_config())
    up = m.map({"collective": 0.7})
    down = m.map({"collective": -0.7})
    assert up.rt > 0 and up.lt == 0
    assert down.lt > 0 and down.rt == 0


def test_buttons_bitmask():
    m = Mapper(load_config())
    axes = m.map({"buttons": 0b101})  # bity 0 a 2
    assert axes.buttons == [0, 2]


def test_invert_flag():
    cfg = load_config()
    cfg["invert"]["roll"] = True
    axes = Mapper(cfg).map({"roll": 0.5})
    assert axes.lx < 0


def test_parse_packet_rejects_garbage():
    assert parse_packet(b"not json") is None
    assert parse_packet(b"[1,2,3]") is None
    assert parse_packet(json.dumps({"roll": 0.1}).encode()) == {"roll": 0.1}


if __name__ == "__main__":
    import sys
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except AssertionError:
                failed += 1
                print("FAIL", name)
    sys.exit(1 if failed else 0)
