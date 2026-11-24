"""The heat-set tool profile (heatsetcore.profile) and settings schema 2.

Rules are the spec's (docs/HEATSET_GCODE_SPEC.md, "Validation: export refuses, naming the
rule"); the worked example is its golden-test input.
"""

import copy
import json

import pytest

from heatsetcore import profile
from nutcore import library


def broken(**change):
    p = profile.default_profile()
    p.update(change)
    return profile.validate_profile(p)


def test_defaults_are_valid_and_fresh():
    assert profile.validate_profile(profile.default_profile()) == []
    assert library.validate(library.default_config()) == []
    p = profile.default_profile()
    p["filament_temps"]["PLA"] = 1.0
    p["tbd"].clear()
    assert profile.default_profile()["filament_temps"]["PLA"] == 225.0
    assert "pad_drop" in profile.default_profile()["tbd"]


def test_defaults_follow_the_answers_of_24_nov():
    p = profile.default_profile()
    assert (p["firmware"], p["timing"], p["insert_temp"]) == ("reprapfirmware", "after_layer",
                                                              None)
    for name in ("magazine_capacity", "min_contact_area", "max_height_ratio"):
        assert name in p["tbd"]
    assert {"magazine_capacity", "tool", "firmware", "pad_drop"} <= set(profile.MACHINE_FIELDS)
    assert "mouth_gap" not in profile.MACHINE_FIELDS        # process, not machine


@pytest.mark.parametrize(("change", "rule"), [
    ({"pad_drop": 0.9}, "rule 1"),                 # pad_drop above mouth_gap
    ({"mouth_gap": 1.2}, "rule 1"),                # mouth_gap above proud_after_hot
    ({"proud_after_hot": 5.7}, "rule 1"),          # proud_after_hot not below insert_length
    ({"rest_recess": -0.1}, "a number, zero or more"),
    ({"travel_lift": 0.6}, "rule 2"),              # below pad_drop + 0.3
    ({"local_clear": 2.0}, "rule 3"),              # below proud_after_hot + 1.0
    ({"push_step": 0.6}, "rule 4"),                # above float_travel / 2
    ({"insert_temp": 300.0}, "rule 6"),
    ({"filament_temps": {"PC": 310.0}}, "rule 6"),
])
def test_each_rule_broken_refuses_naming_it(change, rule):
    errors = broken(**change)
    assert errors and any(rule in e for e in errors), errors


@pytest.mark.parametrize("change", [
    {"insert_key": "M3 x5.7"}, {"insert_key": "M3..5"}, {"name": ""},
    {"firmware": "rrf"}, {"timing": "now"}, {"mode": "dry"}, {"on_proud": "stop"},
    {"insert_length": "5.7"}, {"tool": 2.5}, {"tool": True}, {"magazine_capacity": 0},
    {"hole_d_min": 4.3}, {"tbd": ["pad_drop", "warp_factor"]}, {"tbd": "pad_drop"},
    {"insert_temp": 0}, {"filament_temps": {"PLA": "hot"}}, {"pad_dx": float("nan")},
])
def test_bad_values_are_refused(change):
    assert broken(**change)


def test_rule_5_needs_every_tbd_measured_unless_rehearsing():
    p = profile.default_profile()
    problem = profile.tbd_problem(p)
    assert "rule 5" in problem and "pad_drop" in problem and "magazine_capacity" in problem
    assert profile.tbd_problem(dict(p, mode="rehearse")) is None
    assert profile.tbd_problem(dict(p, tbd=[])) is None


def test_rule_9_magazine_capacity():
    p = profile.default_profile()
    assert profile.magazine_problem(p, 12) is None
    problem = profile.magazine_problem(p, 13)
    assert "rule 9" in problem and "13 inserts" in problem and "holds 12" in problem


def test_insert_temperature_order():
    p = profile.default_profile()
    assert profile.insert_temperature(dict(p, insert_temp=232.0), 220.0, "PLA") == (
        232.0, "manual override")
    temp, source = profile.insert_temperature(p, 220.0, "PLA")
    assert temp == 235.0 and "print temperature" in source
    assert profile.insert_temperature(p, None, "petg")[0] == 245.0     # the filament table
    temp, why = profile.insert_temperature(p, None, "TPU")
    assert temp is None and "TPU" in why
    assert profile.temperature_problem(285.0) is None
    assert "rule 6" in profile.temperature_problem(305.0)


def test_schema_1_settings_migrate_and_keep_the_tuned_nut_library():
    old = library.default_config()
    del old["heatset"]
    old["schema"] = 1
    old["nuts"][0]["flat"]["width"] = [5.65, 5.85]          # tuned by test prints
    old["settings"]["on_error"] = "skip"
    before = json.dumps(old, sort_keys=True)
    new = library.migrate(old)
    assert json.dumps(old, sort_keys=True) == before          # the input is not modified
    assert new["schema"] == 2 and library.validate(new) == []
    assert new["nuts"] == old["nuts"] and new["settings"] == old["settings"]
    assert new["heatset"] == profile.default_section()
    assert library.migrate(new) is new                        # schema 2 stays as it is
    assert library.migrate("not settings") == "not settings"


def test_profiles_are_found_by_insert_key_and_keys_are_unique():
    config = library.default_config()
    second = dict(copy.deepcopy(config["heatset"]["profiles"][0]), name="M4 tool",
                  insert_key="M4x8.1")
    config["heatset"]["profiles"].append(second)
    lib = library.parse(config)
    assert lib.insert_keys() == ["M3x5.7", "M4x8.1"]
    assert lib.heatset_profile("m4X8.1")["name"] == "M4 tool"
    assert lib.heatset_profile("M5x9") is None
    config["heatset"]["profiles"].append(dict(second, name="Copy", insert_key="m4x8.1"))
    assert any("used by another profile" in e for e in library.validate(config))
    config["heatset"]["profiles"][-1] = dict(second)
    assert any("name is used twice" in e for e in library.validate(config))
