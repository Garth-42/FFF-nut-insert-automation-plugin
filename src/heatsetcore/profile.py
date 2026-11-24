"""The heat-set tool profile: defaults, the TBD list, validation and derived values.

One profile per physical tool, stored in the plugin settings under "heatset". The
variables, their placeholders and the rules come from docs/HEATSET_GCODE_SPEC.md
("Slice-time variables"); the additions and changes are listed in docs/heatset-plan.md.
Rule numbers in messages are the spec's ("Validation: export refuses, naming the rule").

Plain Python: nothing here imports numpy, so the settings can be read while Orca loads
the plugin (CLAUDE.md rule 9).
"""

from __future__ import annotations

import copy
import math
import re

FIRMWARES = ("reprapfirmware", "klipper")
TIMINGS = ("after_layer", "end_of_print")
ON_PROUD = ("warn", "pause")
MODES = ("normal", "rehearse")
MAX_INSERT_TEMP = 290.0   # rule 6: the throat heater's firmware limit, °C
KEY_PATTERN = re.compile(r"^[A-Za-z0-9]+([._-][A-Za-z0-9]+)*$")   # M3x5.7
EPS = 1e-9

# The spec's tables, in its order. Values are the spec's defaults; those still to be
# measured are listed in "tbd" and hold the spec's placeholder.
GROUPS = {
    "measured": {
        "insert_key": "M3x5.7", "insert_length": 5.7, "insert_od": 4.6, "rest_recess": 0.0,
        "pad_dx": 20.0, "pad_dy": 0.0, "pad_drop": 0.4, "pad_d": 10.0, "tube_od": 5.5,
        "block_r": 12.0, "block_clearance": 2.5, "trip_overtravel": 0.0, "float_travel": 1.0,
        "trip_force": 650.0,
    },
    "process": {
        "proud_after_hot": 1.1, "mouth_gap": 0.8, "follower_retract": 0.3,
        "insert_temp": None,         # the manual override; None: automatic (insert_temperature)
        "insert_temp_offset": 15.0,  # new: the spec's "print temperature + 10-20 °C"
        "filament_temps": {"PLA": 225.0, "PETG": 245.0, "ABS": 265.0, "ASA": 265.0},
        "temp_window": 5.0, "resist_wait": 2.0, "resist_retries": 3, "press_dwell": 3.0,
        "flush_tol": 0.10, "press_guard": 0.30, "surface_tol": 0.50,
    },
    "motion": {
        "push_step": 0.25, "push_speed": 0.5, "unsheath_speed": 1.0, "retract_speed": 2.0,
        "probe_start": 2.0, "probe_speed": 2.0, "press_speed": 1.0, "travel_lift": 1.5,
        "local_clear": 3.0, "safe_z_clear": 5.0, "xy_travel_speed": 150.0,
        "xy_local_speed": 30.0, "z_travel_speed": 10.0, "z_local_speed": 5.0,
    },
    "behaviour": {
        "tool": 3, "firmware": "reprapfirmware", "timing": "after_layer", "preheat_lead": 120.0,
        "preheat_layers": 2, "on_proud": "warn", "mode": "normal", "rehearse_lift": 10.0,
        "hole_d_min": 3.90, "hole_d_max": 4.20, "hole_extra_depth": 1.0, "min_wall": 1.6,
        "magazine_capacity": 12,      # new: rule 9 needs the number
        "min_contact_area": 100.0,    # new: hold-down warning, mm² on the bed
        "max_height_ratio": 3.0,      # new: hold-down warning, height / sqrt(contact area)
    },
}
TBD = ["rest_recess", "pad_dx", "pad_dy", "pad_drop", "block_r", "block_clearance",
       "trip_overtravel", "float_travel", "trip_force", "tool", "magazine_capacity",
       "min_contact_area", "max_height_ratio"]
# The panel's Machine settings tab: the tool's hardware, apart from the process settings.
MACHINE_FIELDS = (*GROUPS["measured"], *GROUPS["motion"], "tool", "firmware",
                  "magazine_capacity")

_POSITIVE = ("insert_length", "insert_od", "pad_drop", "pad_d", "tube_od", "block_r",
             "float_travel", "trip_force", "proud_after_hot", "mouth_gap", "temp_window",
             "press_dwell", "flush_tol", "press_guard", "surface_tol", *GROUPS["motion"],
             "rehearse_lift", "hole_d_min", "hole_d_max", "min_wall", "min_contact_area",
             "max_height_ratio")
_NON_NEGATIVE = ("rest_recess", "block_clearance", "trip_overtravel", "follower_retract",
                 "resist_wait", "preheat_lead", "hole_extra_depth", "insert_temp_offset")
_ANY_NUMBER = ("pad_dx", "pad_dy")
_WHOLE = {"resist_retries": 0, "preheat_layers": 0, "tool": 0, "magazine_capacity": 1}
_CHOICES = {"firmware": FIRMWARES, "timing": TIMINGS, "on_proud": ON_PROUD, "mode": MODES}
MEASURABLE = (*_POSITIVE, *_NON_NEGATIVE, *_ANY_NUMBER, *_WHOLE)


def default_profile() -> dict:
    """A fresh copy of the default profile, named after the prototype."""
    profile = {"name": "Concept D"}
    for group in GROUPS.values():
        profile.update(copy.deepcopy(group))
    profile["tbd"] = list(TBD)
    return profile


def default_section() -> dict:
    """The "heatset" part of the plugin settings."""
    return {"profiles": [default_profile()]}


def _number(value) -> bool:
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value))


def validate_profile(profile, where: str = "heat-set profile") -> list[str]:
    """What is wrong with one profile, rules 1 to 4 and 6 included. Empty when valid."""
    if not isinstance(profile, dict):
        return [f"{where}: must be an object"]
    errors: list[str] = []
    name = profile.get("name")
    if isinstance(name, str) and name.strip():
        where = f"heat-set profile {name!r}"
    else:
        errors.append(f"{where}: name must be text")
    key = profile.get("insert_key")
    if not isinstance(key, str) or not KEY_PATTERN.match(key):
        errors.append(f"{where}: insert_key must be letters and digits joined by single "
                      ". _ or - characters, for example M3x5.7")
    for field, choices in _CHOICES.items():
        if profile.get(field) not in choices:
            errors.append(f"{where}: {field} must be one of {', '.join(choices)}")

    bad = []
    for fields, ok, rule in ((_POSITIVE, lambda v: v > 0, "a positive number"),
                             (_NON_NEGATIVE, lambda v: v >= 0, "a number, zero or more"),
                             (_ANY_NUMBER, lambda v: True, "a number")):
        for field in fields:
            value = profile.get(field)
            if not _number(value) or not ok(value):
                errors.append(f"{where}: {field} must be {rule}")
                bad.append(field)
    for field, low in _WHOLE.items():
        value = profile.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < low:
            errors.append(f"{where}: {field} must be a whole number, {low} or more")
            bad.append(field)

    temp = profile.get("insert_temp")
    if temp is not None:
        if not _number(temp) or temp <= 0:
            errors.append(f"{where}: insert_temp must be a temperature, or empty for automatic")
        elif temp > MAX_INSERT_TEMP + EPS:
            errors.append(f"{where}: rule 6: insert_temp {temp:g} °C is above the firmware "
                          f"limit of {MAX_INSERT_TEMP:g} °C")
    temps = profile.get("filament_temps")
    if not isinstance(temps, dict) or not all(
            isinstance(k, str) and k.strip() and _number(v) and v > 0 for k, v in temps.items()):
        errors.append(f"{where}: filament_temps must map filament types to temperatures")
    else:
        for filament, value in temps.items():
            if value > MAX_INSERT_TEMP + EPS:
                errors.append(f"{where}: rule 6: filament_temps {filament} {value:g} °C is above "
                              f"the firmware limit of {MAX_INSERT_TEMP:g} °C")
    tbd = profile.get("tbd")
    if not isinstance(tbd, list) or not all(isinstance(n, str) for n in tbd):
        errors.append(f"{where}: tbd must be a list of variable names")
    else:
        unknown = [n for n in tbd if n not in MEASURABLE]
        if unknown:
            errors.append(f"{where}: tbd names unknown variables: {', '.join(unknown)}")

    if bad:
        return errors                   # the rules below need sound numbers
    if profile["hole_d_min"] > profile["hole_d_max"] + EPS:
        errors.append(f"{where}: hole_d_min {profile['hole_d_min']:g} exceeds hole_d_max "
                      f"{profile['hole_d_max']:g}")
    return errors + rule_problems(profile, where)


def rule_problems(profile: dict, where: str = "heat-set profile") -> list[str]:
    """The spec's rules 1 to 4, which tie the variables to each other."""
    li, e = profile["insert_length"], profile["rest_recess"]
    p, h, g = profile["pad_drop"], profile["mouth_gap"], profile["proud_after_hot"]
    lift, clear = profile["travel_lift"], profile["local_clear"]
    out = []
    if not (0 < p < h <= g + EPS and g < li) or e < 0:
        out.append(f"{where}: rule 1: needs 0 < pad_drop < mouth_gap <= proud_after_hot < "
                   f"insert_length and rest_recess >= 0; they are {p:g}, {h:g}, {g:g}, {li:g} "
                   f"and {e:g}")
    if lift < p + 0.3 - EPS:
        out.append(f"{where}: rule 2: travel_lift {lift:g} must be at least pad_drop + 0.3 = "
                   f"{p + 0.3:g}, so the pad clears the insert as it moves over it")
    if clear < g + 1.0 - EPS or clear - p < 1.0 - EPS:
        out.append(f"{where}: rule 3: local_clear {clear:g} must be at least "
                   f"proud_after_hot + 1.0 = {g + 1:g} and pad_drop + 1.0 = {p + 1:g}")
    if profile["push_step"] > profile["float_travel"] / 2 + EPS:
        out.append(f"{where}: rule 4: push_step {profile['push_step']:g} must be at most "
                   f"float_travel / 2 = {profile['float_travel'] / 2:g}")
    return out


def tbd_problem(profile: dict) -> str | None:
    """Rule 5: every TBD set before a normal export. Rehearse mode runs without them."""
    if profile.get("mode") == "rehearse" or not profile.get("tbd"):
        return None
    return (f"heat-set profile {profile.get('name')!r}: rule 5: measure "
            f"{', '.join(profile['tbd'])} and enter them in the Nut panel (Machine settings "
            "and Heat-set tabs), or switch the profile to rehearse mode")


def magazine_problem(profile: dict, count: int) -> str | None:
    """Rule 9: no more inserts in the print than the magazine holds."""
    capacity = profile["magazine_capacity"]
    if count <= capacity:
        return None
    return (f"heat-set profile {profile.get('name')!r}: rule 9: the print has {count} inserts "
            f"and the magazine holds {capacity}. Refilling mid-print is not supported")


def temperature_problem(temp: float) -> str | None:
    """Rule 6 for the temperature a print will use."""
    if temp <= MAX_INSERT_TEMP + EPS:
        return None
    return (f"rule 6: insert temperature {temp:g} °C is above the firmware limit of "
            f"{MAX_INSERT_TEMP:g} °C")


def insert_temperature(profile: dict, print_temp: float | None = None,
                       filament_type: str | None = None) -> tuple[float | None, str]:
    """(temperature, where it came from), or (None, why there is none).

    In order: the manual override; the print temperature found in the G-code plus
    insert_temp_offset; the filament table, by the filament type of the print.
    """
    if profile.get("insert_temp") is not None:
        return float(profile["insert_temp"]), "manual override"
    if print_temp is not None and print_temp > 0:
        offset = float(profile["insert_temp_offset"])
        return (float(print_temp) + offset,
                f"print temperature {print_temp:g} °C + {offset:g} °C")
    if filament_type and filament_type.strip():
        table = {k.strip().upper(): v for k, v in profile["filament_temps"].items()}
        temp = table.get(filament_type.strip().upper())
        if temp is not None:
            return float(temp), f"filament table, {filament_type.strip()}"
    return None, ("no manual override, no print temperature in the G-code, and no "
                  f"filament table entry for {filament_type or 'this filament'}")


def profile_for_key(profiles, key: str | None) -> dict | None:
    """The profile whose insert_key is key, ignoring case."""
    if not key:
        return None
    return next((p for p in profiles if str(p.get("insert_key", "")).upper() == key.upper()),
                None)
