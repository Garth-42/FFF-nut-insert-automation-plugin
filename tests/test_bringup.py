"""The bring-up kit: the air test (heatsetcore.bringup) run in both stand-ins, and the check
macros for RepRapFirmware (macros/heatset/check_*.g) and Klipper (heatset_checks.cfg)."""

import json
from pathlib import Path

import pytest

from heatsetcore import bringup, profile
from klipper_sim import Float as KlipperFloat
from klipper_sim import Klipper
from nutcore import library
from rrf_sim import RRF

ROOT = Path(__file__).parents[1]
MACROS = ROOT / "macros" / "heatset"
KLIPPER = [ROOT / "firmware" / "klipper" / name
           for name in ("heatset_limits.cfg", "heatset_macros.cfg", "heatset_checks.cfg")]
Z = 40.0


def rrf() -> RRF:
    k = RRF(MACROS)
    k.run('M98 P"heatset/init.g"')
    return k


def pad_lowest(k, p) -> float:
    return min(m.z for m in k.moves) - p["pad_drop"]


# --- The air test ---------------------------------------------------------------------------

def test_the_air_test_runs_the_routine_in_the_air_on_rrf():
    p = profile.default_profile()                   # TBDs and an empty magazine are fine
    k = rrf()
    k.float.surface = lambda x, y, n: None          # nothing on the bed
    k.run_file(bringup.air_test(p, 150.0, 150.0, Z))
    assert k.aborted is None and k.dialogs == [] and k.z_probes == 0
    assert k.pos["A"] == 0.0 and k.max_target[2] == 0.0 and k.tool_changes == [3, 0]
    assert pad_lowest(k, p) >= Z + p["probe_start"] - 1e-9
    assert k.fs["0:/sys/heatset/log.csv"].splitlines()[1].endswith(",rehearsed")


def test_the_air_test_wants_a_homed_printer_on_rrf():
    k = rrf()
    k.axes[0]["homed"] = False
    k.run_file(bringup.air_test(profile.default_profile(), 150.0, 150.0, Z))
    assert k.aborted == "Heat-set air test: home X, Y and Z first" and k.moves == []


def test_the_air_test_on_klipper():
    p = {**profile.default_profile(), "firmware": "klipper"}
    k = Klipper(*KLIPPER)
    k.float = KlipperFloat(surface=lambda x, y: None)
    k.run_file(bringup.air_test(p, 150.0, 150.0, Z))
    assert k.pauses == [] and k.probes == 0 and k.pos["A"] == 0.0 and k.max_target == 0.0
    assert pad_lowest(k, p) >= Z + p["probe_start"] - 1e-9
    assert any("rehearsed" in m for _, m in k.messages)


def test_the_air_test_is_always_rehearse_and_never_low():
    p = {**profile.default_profile(), "tbd": [], "mode": "normal"}
    text = bringup.air_test(p, 150.0, 150.0, Z)
    assert 'B"rehearse"' in text and 'B"normal"' not in text
    with pytest.raises(ValueError, match="too low for an air test"):
        bringup.air_test(p, 150.0, 150.0, 2.0)


def test_the_command_line_takes_the_exported_settings(tmp_path, capsys):
    config = library.default_config()
    config["heatset"]["profiles"][0].update({"tool": 4, "pad_dx": 25.0})
    settings = tmp_path / "nut_settings.json"
    settings.write_text(json.dumps(config))
    out = tmp_path / "air_test.gcode"
    assert bringup.main(["--x", "150", "--y", "120", "--settings", str(settings),
                         "--out", str(out)]) == 0
    text = out.read_text()
    assert ' H4 ' in text and "G0 X125.000 Y120.000 F9000" in text     # the pad over the spot
    assert bringup.main(["--x", "150", "--y", "120", "--firmware", "klipper"]) == 0
    assert "HEATSET_CONFIG KEY=M3x5.7 TOOL=3" in capsys.readouterr().out
    assert bringup.main(["--x", "1", "--y", "1", "--settings", str(settings),
                         "--key", "M9x9"]) == 2
    assert "no heat-set profile has key M9x9" in capsys.readouterr().err


# --- RepRapFirmware checks ------------------------------------------------------------------

def test_check_float_sees_the_float_pushed():
    k = rrf()
    k.on_dwell = lambda seconds: setattr(k.float, "tripped", seconds >= 1.0)
    k.run('M98 P"heatset/check_float.g"')
    assert k.messages[-1].startswith("heatset float: OK") and k.moves == []


def test_check_float_reports_no_trip_and_a_float_that_reads_tripped():
    k = rrf()
    k.run('M98 P"heatset/check_float.g"')
    assert "did not trip in 15 seconds" in k.messages[-1] and k.dwell == pytest.approx(15.0)
    k = rrf()
    k.float.stuck = True
    k.run('M98 P"heatset/check_float.g"')
    assert "reads TRIPPED" in k.messages[-1]


def test_check_follower_moves_forward_and_back_when_told():
    k = rrf()
    k.run('M98 P"heatset/check_follower.g" D2 V1')
    assert [m.a for m in k.moves] == [2.0, 0.0]
    assert k.messages[-1] == "heatset follower: A 0.0 to 2.0 and back to 0.0"
    k = rrf()
    k.answers = [1]                                 # Cancel
    k.run('M98 P"heatset/check_follower.g" D2 V1')
    assert k.moves == []


def test_check_probe_reports_the_trip_and_goes_back_up():
    k = rrf()
    k.float.surface = lambda x, y, n: 26.0          # the plate under the pad
    k.run('M98 P"heatset/check_probe.g" D5 V1')
    assert k.messages[-1] == "heatset probe: tripped at Z26.4, 3.6 mm below the start"
    assert k.pos["Z"] == 30.0
    k = rrf()
    k.float.surface = lambda x, y, n: None
    k.run('M98 P"heatset/check_probe.g" D5 V1')
    assert k.messages[-1] == "heatset probe: did not trip within 5 mm" and k.pos["Z"] == 30.0


# --- Klipper checks -------------------------------------------------------------------------

def test_klipper_checks():
    k = Klipper(*KLIPPER)
    k.run("HEATSET_CHECK_FLOAT")
    assert "reads open" in k.messages[-1][1]
    k.float.tripped = True
    k.run("HEATSET_CHECK_FLOAT")
    assert "reads TRIPPED" in k.messages[-1][1]
    k.run("HEATSET_CHECK_FOLLOWER DIST=2 SPEED=1")
    assert [m.a for m in k.moves] == [2.0, 0.0] and k.axis_a
