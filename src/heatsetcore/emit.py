"""The emitted G-code: header, preheat line and blocks, one template set per firmware.

docs/HEATSET_GCODE_SPEC.md, "Emitted G-code". RepRapFirmware comes first, as
docs/heatset-plan.md ("RepRapFirmware design") sets out and Garth approved on 24 Nov 2026:
each spec command is a macro call, M98 P"heatset/<name>.g", with single-letter parameters
that avoid G, M, N, T, P (the spec's rule), R (M98's own) and A (the follower axis). The
hot push is one call: the macro loops on the float itself, so nothing is unrolled. Speeds
keep the spec's mm/s under V, apart from RRF's F in mm/min. Klipper's template set comes in
milestone 9.

Number formats are the spec's: X, Y, Z and other lengths with 3 decimals, F as a whole
number in mm/min, speeds (mm/s) and times (s) with 1 decimal; never exponent form, never
a negative zero. Where to put the lines is placement's job (milestone 4).
"""

from __future__ import annotations

from dataclasses import dataclass

from . import routine
from .profile import GROUPS

EPS = 1e-9


@dataclass(frozen=True)
class Insert:
    """One insert of a block, in the order it is done."""

    object: str      # the label of its object, so the firmware can skip a cancelled one
    x: float         # the hole axis, bed coordinates
    y: float
    z_top: float     # the surface it ends flush with, snapped to the printed layer


@dataclass(frozen=True)
class Block:
    """The inserts done at one point in the print, with one tool visit."""

    number: int                    # b: counted from 1 in the file
    timing: str                    # after_layer or end_of_print
    z_safe: float                  # tallest printed point so far + safe_z_clear
    inserts: tuple[Insert, ...]


# --- Number formats -------------------------------------------------------------------------

def length(value: float) -> str:
    """Lengths and coordinates: 3 decimals."""
    text = f"{value:.3f}"
    return "0.000" if text == "-0.000" else text


def tenth(value: float) -> str:
    """Speeds in mm/s and times in s: 1 decimal."""
    text = f"{value:.1f}"
    return "0.0" if text == "-0.0" else text


def feed(speed: float) -> str:
    """A speed in mm/s as a G-code F word value: whole mm/min."""
    return str(int(round(speed * 60)))


def temperature(value: float) -> str:
    """Whole degrees, or one decimal when there is a fraction."""
    rounded = round(value, 1)
    return str(int(rounded)) if rounded == int(rounded) else f"{rounded:.1f}"


def quoted(text) -> str:
    """An RRF string parameter: in double quotes, with a quote inside written twice."""
    return '"' + one_line(text).replace('"', '""') + '"'


def one_line(text) -> str:
    return " ".join(str(text).split())


_ASCII = str.maketrans({"–": "-", "—": "-", "°": " deg", "²": "2", "÷": "/", "√": "sqrt ",
                        "×": "x"})


def ascii_text(text) -> str:
    """One line of plain ASCII for a G-code comment: finding messages use °, ² and dashes."""
    return one_line(str(text).translate(_ASCII)).encode("ascii", "replace").decode()


def _plain(value) -> str:
    """A profile value for a header comment."""
    if value is None:
        return "auto"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        text = f"{value:.6f}".rstrip("0").rstrip(".")
        return "0" if text in ("", "-0") else text
    if isinstance(value, dict):
        return ", ".join(f"{k} {_plain(v)}" for k, v in value.items()) or "none"
    if isinstance(value, (list, tuple)):
        return ", ".join(_plain(v) for v in value) or "none"
    return one_line(value)


# --- RepRapFirmware -------------------------------------------------------------------------

def _call(name: str, *params: str) -> str:
    return " ".join((f'M98 P"heatset/{name}.g"', *params))


def _rrf_config(p: dict, total: int, temp: float) -> list[str]:
    key = "K" + quoted(p["insert_key"])
    return [
        _call("config", key, f"H{p['tool']}", "D" + length(p["pad_drop"]),
              "O" + length(p["trip_overtravel"]), "U" + length(p["surface_tol"]),
              "W" + temperature(p["temp_window"]), "Q" + quoted(p["on_proud"]),
              "B" + quoted(p["mode"]), "L" + length(p["rehearse_lift"])),
        _call("require", key, f"C{total}", "S" + temperature(temp)),
    ]


def _rrf_preheat(p: dict, temp: float) -> str:
    return _call("preheat", "S" + temperature(temp))


def _rrf_block(p: dict, block: Block, temp: float) -> list[str]:
    d = routine.derived(p)
    n, key = len(block.inserts), p["insert_key"]
    z_local = "V" + tenth(p["z_local_speed"])
    out = [f"; HEATSET block {block.number}: {block.timing}, inserts={n}, key {key}",
           _call("begin", "K" + quoted(key), "S" + temperature(temp),
                 "Z" + length(block.z_safe), f"C{n}")]
    for i, ins in enumerate(block.inserts, start=1):
        m = routine.insert_moves(p, ins.x, ins.y, ins.z_top)
        pad_over_hole = f"G0 X{length(m.pad_over_hole_x)} Y{length(m.pad_over_hole_y)}"
        out += [
            f"; insert {i}/{n} {one_line(ins.object)} X{length(ins.x)} Y{length(ins.y)} "
            f"Ztop{length(ins.z_top)}",
            _call("insert_start", f"I{i}", "O" + quoted(ins.object), "X" + length(ins.x),
                  "Y" + length(ins.y), "Z" + length(ins.z_top)),
            "G90",
            f"G0 Z{length(block.z_safe)} F{feed(p['z_travel_speed'])}",          # 2 travel
            f"{pad_over_hole} F{feed(p['xy_travel_speed'])}",
            f"G0 Z{length(m.approach_z)} F{feed(p['z_local_speed'])}",            # 3 approach
            _call("probe", "V" + tenth(p["probe_speed"])),                         # 4 probe
            _call("z", "H" + length(p["local_clear"]), z_local),                   # 5 line up
            f"G0 X{length(ins.x)} Y{length(ins.y)} F{feed(p['xy_local_speed'])}",
            _call("z", "H" + length(p["mouth_gap"]), z_local),
            _call("push", "D" + length(d["push"]), "V" + tenth(p["push_speed"]),   # 6 hot push
                  "W" + tenth(p["resist_wait"]), f"C{p['resist_retries']}"),
        ]
        if d["L"] > EPS:                                                           # 7 unsheath
            out.append(_call("unsheath", "D" + length(d["L"]), "V" + tenth(p["unsheath_speed"])))
        out += [
            _call("retract", "D" + length(p["follower_retract"]),                 # 8 retract
                  "V" + tenth(p["retract_speed"])),
            _call("z", "H" + length(m.lift_height), z_local),                      # 9 lift, swap
            f"{pad_over_hole} F{feed(p['xy_local_speed'])}",
            _call("press", "V" + tenth(p["press_speed"]), "W" + tenth(p["press_dwell"]),
                  "U" + length(p["flush_tol"]), "L" + length(p["press_guard"])),  # 10 press
            _call("z", "H" + length(p["local_clear"]), z_local),                   # 11 finish
            _call("insert_done"),
        ]
    out.append(_call("end"))
    return out


_RRF = {"config": _rrf_config, "preheat": _rrf_preheat, "block": _rrf_block}


def _templates(profile: dict) -> dict:
    if profile["firmware"] == "reprapfirmware":
        return _RRF
    raise NotImplementedError(
        f"the {profile['firmware']} heat-set G-code comes in milestone 9 "
        "(docs/heatset-plan.md); set the heat-set profile's firmware to reprapfirmware")


# --- What placement calls -------------------------------------------------------------------

def header_lines(profile: dict, total_inserts: int, temp: float, version: str,
                 temp_source: str = "") -> list[str]:
    """The header: every profile value and derived value as a comment, then the
    configuration and requirement commands."""
    lines = [f"; HEATSET profile {quoted(profile['name'])} heatsetcore {version}"]
    names = ["name", *(n for group in GROUPS.values() for n in group), "tbd"]
    lines += [f"; {n} = {_plain(profile[n])}" for n in names]
    lines += [f"; {n} = {_plain(v)}" for n, v in routine.derived(profile).items()]
    used = f"; insert_temp_used = {temperature(temp)}"
    source = ascii_text(temp_source.replace("°", ""))      # keep the G-code ASCII
    lines.append(used + (f" ({source})" if source else ""))
    return lines + _templates(profile)["config"](profile, total_inserts, temp)


def preheat_line(profile: dict, temp: float) -> str:
    return _templates(profile)["preheat"](profile, temp)


def block_lines(profile: dict, block: Block, temp: float) -> list[str]:
    """One block: begin, the routine for each insert, end."""
    return _templates(profile)["block"](profile, block, temp)
