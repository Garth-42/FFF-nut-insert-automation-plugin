"""The Klipper heat-set commands, firmware/klipper/heatset_macros.cfg, run on the G-code the
emitter writes, in tests/klipper_sim.py's stand-in for Klipper.

A print here is the header, a preheat and one end_of_print block of two inserts, z_top 12.4,
with the default profile (its TBD placeholders taken as measured) and the Klipper templates.
The float model: the first probe of each insert lands on the part, the press on the insert.
"""

import re
from pathlib import Path

import pytest

from heatsetcore import emit, profile, routine
from klipper_sim import Float, Klipper, KlipperError

CFG = Path(__file__).parents[1] / "firmware" / "klipper"
LIMITS, MACROS = CFG / "heatset_limits.cfg", CFG / "heatset_macros.cfg"
Z_TOP = 12.4


def prof(**change) -> dict:
    p = {**profile.default_profile(), "tbd": [], "firmware": "klipper", **change}
    assert profile.validate_profile(p) == []
    return p


def inserts(*objects):
    objects = objects or ("bracket_1", "bracket_1")
    return tuple(emit.Insert(name, 120.0 + 20 * i, 80.0, Z_TOP) for i, name in enumerate(objects))


def print_text(p, block=None, temp=245.0) -> str:
    block = block or inserts()
    lines = emit.header_lines(p, len(block), temp, "test") + [emit.preheat_line(p, temp)]
    lines += emit.block_lines(p, emit.Block(1, "end_of_print", routine.z_safe(p, Z_TOP), block),
                              temp)
    return "\n".join(lines) + "\n"


def printer(p, count=12, key="M3x5.7", proud=0.0, surface=None) -> Klipper:
    k = Klipper(LIMITS, MACROS)
    k.save_vars.update({"hs_count": count, "hs_key": key})

    def landed(x, y):            # the probe on the part, then the press on the insert
        return Z_TOP if k.probes % 2 == 0 else Z_TOP + proud

    k.float = Float(pad_drop=p["pad_drop"], overtravel=p["trip_overtravel"], pad_dx=p["pad_dx"],
                    pad_dy=p["pad_dy"], surface=surface or landed)
    return k


def xy_heights(k) -> float:
    """The lowest mouth height of any move that changes X or Y."""
    return min(m.z for m in k.moves if m.xy)


# --- A print as it should go ----------------------------------------------------------------

def test_a_print_inserts_both_and_keeps_count():
    p = prof()
    k = printer(p)
    k.run_file(print_text(p))
    assert k.pauses == [] and k.probes == 4               # probe and press, twice
    assert k.save_vars["hs_count"] == 10
    assert k.save_vars["hs_pending"] == pytest.approx(p["follower_retract"])
    d = routine.derived(p)
    r = p["follower_retract"]
    assert k.pos["A"] == pytest.approx((d["push"] + d["L"] - r) + (r + d["push"] + d["L"] - r))
    assert (k.tool, k.heater["target"], k.axis_a) == (0, 0.0, True)
    assert k.max_target == 245.0
    state = k.macros["_HS_STATE"][1]
    assert (state["in_block"], state["left"], state["skip"]) == (False, 0, False)
    assert state["s"] == pytest.approx(Z_TOP) and state["proud"] == pytest.approx(0.0)
    assert xy_heights(k) >= Z_TOP + p["proud_after_hot"] + p["travel_lift"] - 1e-9
    assert sum("rehearse" in m for _, m in k.messages) == 0


def test_heights_follow_the_spec_table():
    """Mouth heights above s after each step: 0.8 in the push, 1.1 after the unsheath."""
    p = prof()
    k = printer(p)
    k.run_file(print_text(p, inserts("bracket_1")))
    zs = [round(m.z - Z_TOP, 3) for m in k.moves]
    assert zs[zs.index(0.8):zs.index(0.8) + 2] == [0.8, 0.8]     # line up, then the push in A
    assert 1.1 in zs and 2.6 in zs and 0.4 in zs                 # unsheath, lift, press trip


def test_two_prints_in_a_row():
    p = prof()
    k = printer(p)
    k.run_file(print_text(p))
    k.run_file(print_text(p))                  # axis A is registered once only
    assert k.save_vars["hs_count"] == 8 and k.pauses == []


# --- Rehearse mode --------------------------------------------------------------------------

def test_rehearse_never_heats_pushes_probes_or_touches():
    p = prof(mode="rehearse", tbd=["pad_dx", "tool"])
    k = printer(p, count=0)                       # an empty magazine is fine
    k.run_file(print_text(p))
    assert k.pauses == [] and k.probes == 0
    assert (k.pos["A"], k.axis_a, k.max_target) == (0.0, False, 0.0)
    assert k.save_vars["hs_count"] == 0
    pad_lowest = min(m.z for m in k.moves) - p["pad_drop"]
    assert pad_lowest >= Z_TOP + p["probe_start"] - 1e-9       # the approach, 2 mm above
    assert sum("rehearsed" in m for _, m in k.messages) == 2


# --- When something goes wrong --------------------------------------------------------------

def test_a_warped_surface_stops_that_insert_and_resume_goes_on_clear_of_the_part():
    p = prof()
    k = printer(p, surface=lambda x, y: Z_TOP + 1.0 if abs(x - 120.0) < 1 else Z_TOP)
    k.run_file(print_text(p))
    assert len(k.pauses) == 1 and "insert 1 stopped" in k.pauses[0]
    assert "surface is at Z13.4, not Z12.4" in k.pauses[0]
    assert k.save_vars["hs_count"] == 11                      # only the second insert
    assert xy_heights(k) >= Z_TOP + 2.6 - 1e-9                # no XY move with the pad down


def test_an_insert_that_keeps_resisting_is_stopped_after_its_waits():
    p = prof()
    k = printer(p)
    k.float.resist = [False, False, False] + [True] * 4     # trips after the third step
    k.run_file(print_text(p))
    assert len(k.pauses) == 1 and "still resists after 3 waits" in k.pauses[0]
    assert k.dwell == pytest.approx(3 * p["resist_wait"] + p["press_dwell"])   # 1 press
    assert k.save_vars["hs_count"] == 11
    assert xy_heights(k) >= Z_TOP + 2.6 - 1e-9


def test_a_short_wait_while_it_resists_then_it_goes_in():
    p = prof()
    k = printer(p)
    k.float.resist = [False, True, False]
    k.run_file(print_text(p))
    assert k.pauses == [] and k.save_vars["hs_count"] == 10
    assert k.macros["_HS_STATE"][1]["waits"] == 0 and k.dwell >= p["resist_wait"]


def test_an_excluded_object_skips_its_insert():
    p = prof()
    k = printer(p)
    k.excluded = ["LID_2"]
    k.run_file(print_text(p, inserts("bracket_1", "lid_2")))
    assert k.pauses == [] and k.probes == 2 and k.save_vars["hs_count"] == 11
    assert any("skipped, its object is excluded" in m for _, m in k.messages)


def test_a_float_stuck_tripped_stops_the_insert_before_it_moves_down():
    p = prof()
    k = printer(p)
    k.float.tripped = True
    k.run_file(print_text(p))
    assert len(k.pauses) == 2 and all("stuck float or debris" in x for x in k.pauses)
    assert k.probes == 0 and k.save_vars["hs_count"] == 12


def test_a_short_magazine_asks_for_a_refill():
    p = prof()
    k = printer(p, count=1)
    k.run_file(print_text(p))
    assert "HEATSET_REFILL KEY=M3x5.7 COUNT=n" in k.pauses[0]      # at the header
    assert k.save_vars["hs_count"] == 0                             # one insert went in
    assert any("the magazine is empty" in x for x in k.pauses)      # the other is stopped


def test_the_wrong_inserts_loaded_ask_for_a_refill():
    p = prof()
    k = printer(p, key="M4x8")
    k.run_file(print_text(p))
    assert "the magazine has 0 M3x5.7 inserts" in k.pauses[0]


def test_a_cold_throat_pauses_and_the_insert_is_stopped():
    p = prof()
    k = printer(p)
    k.heater_follows = False                    # the throat stays at room temperature
    k.run_file(print_text(p))
    assert "the throat is at 20.0 C and needs 245.0 C" in k.pauses[0]
    assert k.probes == 0 and k.save_vars["hs_count"] == 12
    assert k.dwell >= 3 * 60                    # the block and each insert waited


@pytest.mark.parametrize(("on_proud", "pauses"), [("warn", 0), ("pause", 2)])
def test_a_proud_insert_warns_or_pauses(on_proud, pauses):
    p = prof(on_proud=on_proud)
    k = printer(p, proud=0.3)
    k.run_file(print_text(p))
    assert len(k.pauses) == pauses and k.save_vars["hs_count"] == 10
    assert sum("is 0.3 mm proud, over 0.1 mm" in m for _, m in k.messages) == 2


def test_an_overpressed_insert_warns():
    p = prof()
    k = printer(p, proud=-0.5)
    k.run_file(print_text(p))
    assert k.pauses == [] and sum("pressed 0.5 mm below" in m for _, m in k.messages) == 2


# --- Refusals -------------------------------------------------------------------------------

@pytest.mark.parametrize(("change", "message"), [
    ({"mode": "fast"}, "MODE must be normal or rehearse"),
    ({"tool": 7}, "tool 7 has no tool_number"),
])
def test_the_header_refuses_bad_values(change, message):
    p = prof()
    text = print_text(p)
    line = next(x for x in text.splitlines() if x.startswith("HEATSET_CONFIG"))
    for key, value in change.items():
        name = {"mode": "MODE", "tool": "TOOL"}[key]
        line = re.sub(rf"{name}=\S+", f"{name}={value}", line)
    with pytest.raises(KlipperError, match=message):
        printer(p).run(line)


def test_routine_commands_refuse_outside_a_block():
    k = printer(prof())
    for line in ("HEATSET_Z HEIGHT=1 SPEED=5", "_HS_PUSH_TICK", "HEATSET_INSERT_DONE"):
        with pytest.raises(KlipperError, match="outside HEATSET_BEGIN"):
            k.run(line)


def test_temperatures_over_the_limit_are_refused():
    p = prof()
    k = printer(p)
    k.run(next(x for x in print_text(p).splitlines() if x.startswith("HEATSET_CONFIG")))
    with pytest.raises(KlipperError, match="outside the limit of 290.0 C"):
        k.run("HEATSET_REQUIRE KEY=M3x5.7 COUNT=1 TEMP=300")


def test_refill_sets_the_magazine():
    k = printer(prof(), count=0, key="")
    k.run("HEATSET_REFILL KEY=M3x5.7 COUNT=12")
    assert (k.save_vars["hs_key"], k.save_vars["hs_count"]) == ("M3x5.7", 12)


# --- The file itself ------------------------------------------------------------------------

def gcode_blocks(path: Path) -> dict[str, str]:
    """Each [gcode_macro] section's gcode, as written in the file."""
    out, name, lines = {}, None, []
    for raw in path.read_text().splitlines() + ["[end]"]:
        if raw.startswith("["):
            if name:
                out[name] = "\n".join(lines)
            found = re.match(r"\[gcode_macro (\w+)\]", raw)
            name, lines, inside = (found[1] if found else None), [], False
        elif name and raw.startswith("gcode:"):
            inside = True
        elif name and inside and raw.startswith("  "):
            lines.append(raw)
    return out


def test_every_command_the_emitter_writes_is_a_macro_reading_its_parameters():
    blocks = gcode_blocks(MACROS)
    calls = [x for x in print_text(prof()).splitlines()
             if re.match(r"(HEATSET_|_HS_)", x)]
    assert {x.split()[0] for x in calls} == {
        "HEATSET_CONFIG", "HEATSET_REQUIRE", "HEATSET_PREHEAT", "HEATSET_BEGIN",
        "HEATSET_INSERT_START", "HEATSET_PROBE", "HEATSET_Z", "_HS_PUSH_START",
        "_HS_PUSH_TICK", "_HS_PUSH_END", "HEATSET_UNSHEATH", "HEATSET_RETRACT",
        "HEATSET_PRESS", "HEATSET_INSERT_DONE", "HEATSET_END"}
    for line in calls:
        name, *args = line.split()
        passed = {a.split("=", 1)[0] for a in args}
        read = set(re.findall(r"params\.([A-Z_]+)", blocks[name]))
        assert passed == read, (name, passed, read)


def test_templates_keep_clear_of_what_klipper_cuts():
    """A ; ends a G-code line in Klipper and a # after a space ends a config value. With
    Klipper's { } delimiters, {- and -} are Jinja whitespace control: {-x} renders x."""
    blocks = {name: text for path in (LIMITS, MACROS, CFG / "heatset_checks.cfg")
              for name, text in gcode_blocks(path).items()}
    assert {"_HS_LIMITS", "HEATSET_CONFIG", "HEATSET_CHECK_FLOAT"} <= set(blocks)
    for name, text in blocks.items():
        for line in text.splitlines():
            assert ";" not in line, (name, line)
            assert not re.search(r"\s#", line), (name, line)
            assert "{-" not in line and "-}" not in line, (name, line)


def test_state_variables_set_are_declared():
    text = MACROS.read_text()
    declared = set(re.findall(r"^variable_(\w+):", text.split("[gcode_macro _HS_SET]")[0],
                              re.MULTILINE))
    for args in re.findall(r"_HS_SET ([^\n{]*)", text):
        for name in re.findall(r"([A-Z_0-9]+)=", args):
            assert name.lower() in declared, name
    for name in re.findall(r"MACRO=_HS_STATE VARIABLE=(\w+)", text):
        assert name in declared, name
    assert all("description:" in block for block in text.split("[gcode_macro ")[1:])
