"""The RepRapFirmware heat-set macros, macros/heatset/*.g, run on the G-code the emitter
writes, in tests/rrf_sim.py's stand-in for RepRapFirmware 3.6.

As in tests/test_klipper_macros.py: a print is the header, a preheat and one end_of_print
block of two inserts, z_top 12.4, with the default profile (its TBDs taken as measured). The
printer starts as config.g leaves it: heatset/init.g run, the magazine refilled. Dialogs are
answered from a script; unscripted, the first choice ("Go on", "Refilled").
"""

from pathlib import Path

import pytest

from heatsetcore import emit, profile, routine
from rrf_sim import RRF, Float, RRFAbort, RRFError

MACROS = Path(__file__).parents[1] / "macros" / "heatset"
Z_TOP = 12.4
THROAT, PRINT_HEATER = 2, 1


def prof(**change) -> dict:
    p = {**profile.default_profile(), "tbd": [], **change}
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


def printer(p, count=12, key="M3x5.7", proud=0.0, surface=None) -> RRF:
    k = RRF(MACROS)
    k.run('M98 P"heatset/init.g"')                    # config.g's last line
    k.run(f'M98 P"heatset/refill.g" K"{key}" C{count}')

    def landed(x, y, n):        # the probe on the part, then the press on the insert
        return Z_TOP if n % 2 == 0 else Z_TOP + proud

    k.float = Float(pad_drop=p["pad_drop"], overtravel=p["trip_overtravel"], pad_dx=p["pad_dx"],
                    pad_dy=p["pad_dy"], surface=surface or landed)
    return k


def xy_heights(k) -> float:
    """The lowest mouth height of any move that changes X or Y."""
    return min(m.z for m in k.moves if m.xy)


def log_rows(k) -> list[list[str]]:
    rows = k.fs["0:/sys/heatset/log.csv"].splitlines()
    assert rows[0] == "index,key,x,y,surface_minus_z_top,waits,proud,outcome"
    return [row.split(",") for row in rows[1:]]


def choices(k) -> list[str]:
    """The texts of the dialogs that asked a question."""
    return [text for mode, _, text in k.dialogs if mode == 4]


# --- A print as it should go ----------------------------------------------------------------

def test_a_print_inserts_both_and_keeps_count():
    p = prof()
    k = printer(p)
    k.run_file(print_text(p))
    assert k.aborted is None and k.dialogs == [] and k.z_probes == 4
    g = k.globals
    assert (g["hs_count"], g["hs_in_block"], g["hs_left"]) == (10, False, 0)
    assert g["hs_pending_retract"] == pytest.approx(p["follower_retract"])
    d, r = routine.derived(p), p["follower_retract"]
    assert k.pos["A"] == pytest.approx((d["push"] + d["L"] - r) + (r + d["push"] + d["L"] - r))
    assert k.current_tool == 0 and k.tool_changes == [3, 0]
    assert k.max_target[THROAT] == 245.0 and k.heater_target(THROAT) == 0.0
    assert [row[-1] for row in log_rows(k)] == ["done", "done"]
    assert "set global.hs_count = 10" in k.fs["0:/sys/heatset/count.g"]
    assert xy_heights(k) >= Z_TOP + p["proud_after_hot"] + p["travel_lift"] - 1e-9


def test_heights_follow_the_spec_table():
    p = prof()
    k = printer(p)
    k.run_file(print_text(p, inserts("bracket_1")))
    zs = [round(m.z - Z_TOP, 3) for m in k.moves]
    assert zs[zs.index(0.8):zs.index(0.8) + 2] == [0.8, 0.8]     # line up, then the push in A
    assert 1.1 in zs and 2.6 in zs and 0.4 in zs                 # unsheath, lift, press trip
    assert float(log_rows(k)[0][4]) == pytest.approx(0.0)        # s - z_top


def test_the_magazine_survives_a_restart():
    p = prof()
    k = printer(p)
    k.run_file(print_text(p))
    again = RRF(MACROS)
    again.fs.update({path: text for path, text in k.fs.items() if path.endswith("count.g")})
    again.run('M98 P"heatset/init.g"')
    assert (again.globals["hs_count"], again.globals["hs_loaded_key"]) == (10, "M3x5.7")
    assert again.globals["hs_pending_retract"] == pytest.approx(p["follower_retract"])


def test_two_prints_in_a_row():
    p = prof()
    k = printer(p)
    k.run_file(print_text(p))
    k.run_file(print_text(p))
    assert k.aborted is None and k.globals["hs_count"] == 8 and len(log_rows(k)) == 4


# --- Rehearse mode --------------------------------------------------------------------------

def test_rehearse_never_heats_pushes_probes_or_touches():
    p = prof(mode="rehearse", tbd=["pad_dx", "tool"])
    k = printer(p, count=0)                       # an empty magazine is fine
    k.run_file(print_text(p))
    assert k.aborted is None and k.dialogs == [] and k.z_probes == 0
    assert k.pos["A"] == 0.0 and k.max_target[THROAT] == 0.0
    assert k.globals["hs_count"] == 0
    pad_lowest = min(m.z for m in k.moves) - p["pad_drop"]
    assert pad_lowest >= Z_TOP + p["probe_start"] - 1e-9         # the approach, 2 mm above
    assert [row[-1] for row in log_rows(k)] == ["rehearsed", "rehearsed"]


# --- When something goes wrong --------------------------------------------------------------

def warped(x, y, n):
    return Z_TOP + 1.0 if abs(x - 120.0) < 1 else Z_TOP


def test_a_warped_surface_asks_and_go_on_skips_that_insert_clear_of_the_part():
    p = prof()
    k = printer(p, surface=warped)
    k.run_file(print_text(p))
    assert k.aborted is None and len(choices(k)) == 1
    assert "surface at Z13.4, not Z12.4" in choices(k)[0]
    assert k.globals["hs_count"] == 11
    assert [row[-1] for row in log_rows(k)] == ["skipped", "done"]
    assert xy_heights(k) >= Z_TOP + 2.6 - 1e-9                 # no XY move with the pad down
    assert k.max_target[THROAT] == 245.0 and k.heater_target(THROAT) == 0.0


def test_stop_the_print_ends_it_with_the_heaters_off():
    p = prof()
    k = printer(p, surface=warped)
    k.answers = [1]                                             # Stop the print
    k.run_file(print_text(p))
    assert k.aborted.startswith("Heat-set: print stopped. surface at Z13.4")
    assert k.heater_target(THROAT) == 0.0 and k.heater_target(PRINT_HEATER) == 0.0
    assert k.globals["hs_count"] == 12


def test_an_insert_that_resists_waits_then_goes_in():
    p = prof()
    k = printer(p)
    k.float.resist_at, k.float.soften_waits = 3.0, 2
    k.run_file(print_text(p))
    assert k.dialogs == [] and k.globals["hs_count"] == 10
    assert log_rows(k)[0][5] == "2" and k.dwell >= 2 * p["resist_wait"]


def test_an_insert_that_keeps_resisting_is_stopped_after_its_waits():
    p = prof()
    k = printer(p)
    k.float.resist_at, k.float.soften_waits = 3.0, 10
    k.run_file(print_text(p))
    assert len(choices(k)) == 1 and "still resists after 3 waits" in choices(k)[0]
    assert k.globals["hs_count"] == 11
    assert [row[-1] for row in log_rows(k)] == ["skipped", "done"]
    assert xy_heights(k) >= Z_TOP + 2.6 - 1e-9


def test_a_cancelled_object_skips_its_insert():
    p = prof()
    k = printer(p)
    k.objects = [{"name": "bracket_1", "cancelled": False}, {"name": "lid_2", "cancelled": True}]
    k.run_file(print_text(p, inserts("bracket_1", "lid_2")))
    assert k.dialogs == [] and k.z_probes == 2 and k.globals["hs_count"] == 11
    assert any("object lid_2 is cancelled" in m for m in k.messages)


def test_a_float_stuck_tripped_stops_each_insert_before_it_moves_down():
    p = prof()
    k = printer(p)
    k.float.stuck = True
    k.run_file(print_text(p))
    assert len(choices(k)) == 2 and all("stuck float or debris" in c for c in choices(k))
    assert k.z_probes == 0 and k.globals["hs_count"] == 12


def test_a_short_magazine_asks_for_a_refill_and_the_count():
    p = prof()
    k = printer(p, count=1)
    k.answers = [0, 12]                                         # Refilled, then 12 loaded
    k.run_file(print_text(p))
    assert "Needs 2 M3x5.7 inserts and has 1." in choices(k)[0]
    assert k.dialogs[1][0] == 5                                 # the count prompt
    assert k.globals["hs_count"] == 10 and k.aborted is None


def test_a_print_can_go_on_without_inserts():
    p = prof()
    k = printer(p, count=1)
    k.answers = [1]                                             # Go on without
    k.run_file(print_text(p))
    assert k.aborted is None and k.z_probes == 0 and k.tool_changes == []
    assert k.globals["hs_count"] == 1 and k.max_target[THROAT] == 0.0
    assert [row[-1] for row in log_rows(k)] == ["skipped", "skipped"]


def test_the_wrong_inserts_loaded_ask_for_a_refill():
    p = prof()
    k = printer(p, key="M4x8")
    k.answers = [2]                                             # Stop the print
    k.run_file(print_text(p))
    assert "and has 0." in choices(k)[0] and k.aborted.startswith("Heat-set: print stopped")


def test_a_cold_throat_stops_the_block():
    p = prof()
    k = printer(p)
    k.heater_follows = False                    # the throat stays at room temperature
    k.run_file(print_text(p))
    assert len(choices(k)) == 1 and "throat at 20.0 C, needs 245 C" in choices(k)[0]
    assert k.dialogs[0][1] == "Heat-set block"
    assert k.dwell >= 60 and k.z_probes == 0 and k.globals["hs_count"] == 12


@pytest.mark.parametrize(("on_proud", "mode"), [("warn", 1), ("pause", 4)])
def test_a_proud_insert_warns_or_asks(on_proud, mode):
    p = prof(on_proud=on_proud)
    k = printer(p, proud=0.3)
    k.run_file(print_text(p))
    shown = [text for m, _, text in k.dialogs if m == mode]
    assert len(shown) == 2 and all("0.3 mm proud, over 0.1 mm" in t for t in shown)
    assert k.globals["hs_count"] == 10


def test_an_overpressed_insert_warns():
    p = prof()
    k = printer(p, proud=-0.5)
    k.run_file(print_text(p))
    assert sum("pressed 0.5 mm below the surface" in t for _, _, t in k.dialogs) == 2


def test_the_follower_at_its_end_stops_the_insert():
    p = prof()
    k = printer(p)
    next(a for a in k.axes if a["letter"] == "A")["max"] = 8.0
    k.run_file(print_text(p))
    assert len(choices(k)) == 1 and "axis A maximum" in choices(k)[0]
    assert k.globals["hs_count"] == 11


# --- Refusals -------------------------------------------------------------------------------

def test_the_header_refuses_bad_values():
    p = prof()
    k = printer(p)
    k.run_file(print_text(p).replace('B"normal"', 'B"fast"'))
    assert k.aborted == "heatset/config.g: B (mode) must be normal or rehearse"
    k = printer(p)
    k.run_file(print_text(p).replace(" H3 ", " H7 "))
    assert k.aborted == "heatset/config.g: tool 7 is not defined (M563)"


def test_an_unhomed_follower_is_refused_before_printing():
    p = prof()
    k = printer(p)
    next(a for a in k.axes if a["letter"] == "A")["homed"] = False
    k.run_file(print_text(p))
    assert k.aborted == "heatset/require.g: home the follower (axis A) before printing"
    assert k.moves == []


def test_routine_macros_refuse_outside_a_block():
    k = printer(prof())
    for line in ('M98 P"heatset/z.g" H1 V5', 'M98 P"heatset/push.g" D1 V1 W1 C1',
                 'M98 P"heatset/insert_done.g"'):
        with pytest.raises(RRFAbort, match="outside a heatset/begin.g"):
            k.run(line)


def test_temperatures_over_the_limit_are_refused():
    p = prof()
    k = printer(p)
    k.run_file(print_text(p, temp=300.0))
    assert k.aborted == "heatset/require.g: 300 C is outside the limit of 290.0 C"


def test_without_init_the_header_says_what_to_add():
    k = RRF(MACROS)
    k.run_file(print_text(prof()))
    assert 'add M98 P"heatset/init.g" to the end of /sys/config.g' in k.aborted


def test_the_stand_in_is_strict():
    """A macro reaching past the stand-in fails, rather than passing by accident."""
    k = RRF(MACROS)
    with pytest.raises(RRFError, match="not in the stand-in"):
        k.run("M104 S200")
    with pytest.raises(RRFError, match="expected a boolean"):
        k.run("if 1\n  echo 1")
