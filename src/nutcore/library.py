"""Settings: the nut library, general settings, defaults and validation.

The settings are one JSON document (see docs/SPEC.md, "data contracts").
`default_config()` returns the document as a plain dict, `validate()` lists what
is wrong with one, and `parse()` turns a valid one into typed objects.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass

from .gcode import templates

SCHEMA = 1
FIRMWARES = ("klipper", "reprapfirmware", "marlin")
KEY_PATTERN = re.compile(r"^[A-Za-z0-9]+(_[A-Za-z0-9]+)*$")

_DEFAULT = {
    "schema": SCHEMA,
    "settings": {
        "axis_tolerance_deg": 0.5,
        "body_tolerance_mm": 0.05,
        "min_top_clearance_mm": 0.1,
        "on_error": "block",
        "firmware": "auto",
        "templates": {
            "klipper": "INSERT_NUT KEY={key} CLASS={cls} X={x} Y={y} Z={z} Z_LOW={z_low} "
                       "YAW={yaw} FEEDER={feeder} TOOL={tool}",
            "reprapfirmware": 'M98 P"insert_nut.g" K"{key}" C"{cls}" X{x} Y{y} Z{z} '
                              "L{z_low} A{yaw} F{feeder} S{tool}",
            "marlin": "",
        },
    },
    "nuts": [
        {
            "key": "M3SQ",
            "label": "M3 square nut, DIN 562",
            "shape": "square",
            "across_flats": 5.5,
            "thickness": 1.8,
            "feeder": 1,
            "max_roof_span": 6.0,
            "tool_reach": 3.0,
            "flat": {"enabled": True, "width": [5.7, 5.9], "depth": [2.0, 2.6]},
            "edge": {"enabled": True, "thickness": [2.0, 2.3], "width": [5.7, 5.9],
                     "height_min": 5.7},
            "corner": {"enabled": True, "thickness": [2.0, 2.3], "opening": [7.98, 8.18],
                       "seat_gap_max": 0.2, "height_min": 7.98},
        }
    ],
}


def default_config() -> dict:
    """A fresh copy of the default settings. Every pocket number is a placeholder."""
    return copy.deepcopy(_DEFAULT)


class ConfigError(ValueError):
    """Raised by parse() when the settings are not valid."""

    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


@dataclass(frozen=True)
class Settings:
    axis_tolerance_deg: float
    body_tolerance_mm: float
    min_top_clearance_mm: float
    on_error: str
    firmware: str
    templates: dict


@dataclass(frozen=True)
class FlatSpec:
    enabled: bool
    width: tuple[float, float]
    depth: tuple[float, float]


@dataclass(frozen=True)
class EdgeSpec:
    enabled: bool
    thickness: tuple[float, float]
    width: tuple[float, float]
    height_min: float


@dataclass(frozen=True)
class CornerSpec:
    enabled: bool
    thickness: tuple[float, float]
    opening: tuple[float, float]
    seat_gap_max: float
    height_min: float


@dataclass(frozen=True)
class NutType:
    key: str
    label: str
    shape: str
    across_flats: float
    thickness: float
    feeder: int
    max_roof_span: float
    tool_reach: float
    flat: FlatSpec
    edge: EdgeSpec
    corner: CornerSpec

    def class_enabled(self, cls: str) -> bool:
        return {"FLAT": self.flat, "EDGE": self.edge, "CORNER": self.corner}[cls].enabled


@dataclass(frozen=True)
class Library:
    settings: Settings
    nuts: dict[str, NutType]  # upper-case key -> nut type

    def keys(self) -> list[str]:
        return [nut.key for nut in self.nuts.values()]

    def get(self, key: str | None) -> NutType | None:
        return self.nuts.get(key.upper()) if key else None


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _check_positive(errors, where, data, name, allow_zero=False):
    value = data.get(name) if isinstance(data, dict) else None
    if not _is_number(value):
        errors.append(f"{where}: {name} must be a number")
    elif value < 0 or (value == 0 and not allow_zero):
        errors.append(f"{where}: {name} must be {'zero or more' if allow_zero else 'positive'}")


def _check_range(errors, where, data, name):
    value = data.get(name) if isinstance(data, dict) else None
    if (not isinstance(value, (list, tuple)) or len(value) != 2
            or not all(_is_number(v) for v in value)):
        errors.append(f"{where}: {name} must be [min, max]")
        return
    if value[0] <= 0 or value[1] <= 0:
        errors.append(f"{where}: {name} sizes must be positive")
    if value[0] > value[1]:
        errors.append(f"{where}: {name} minimum {value[0]} exceeds maximum {value[1]}")


def validate(config) -> list[str]:
    """Return a list of problems. An empty list means the settings are valid."""
    errors: list[str] = []
    if not isinstance(config, dict):
        return ["settings must be a JSON object"]
    if config.get("schema") != SCHEMA:
        errors.append(f"schema must be {SCHEMA}")

    settings = config.get("settings")
    if not isinstance(settings, dict):
        errors.append("settings: missing")
    else:
        _check_positive(errors, "settings", settings, "axis_tolerance_deg")
        _check_positive(errors, "settings", settings, "body_tolerance_mm")
        _check_positive(errors, "settings", settings, "min_top_clearance_mm", allow_zero=True)
        if settings.get("on_error") not in ("block", "skip"):
            errors.append("settings: on_error must be block or skip")
        if settings.get("firmware") not in ("auto", *FIRMWARES):
            errors.append("settings: firmware must be auto, klipper, reprapfirmware or marlin")
        tmpl = settings.get("templates")
        if not isinstance(tmpl, dict):
            errors.append("settings: templates missing")
        else:
            for name in FIRMWARES:
                text = tmpl.get(name)
                if not isinstance(text, str):
                    errors.append(f"settings: template {name} must be text")
                    continue
                problem = templates.check_template(text)
                if problem:
                    errors.append(f"E_TEMPLATE: {name} template: {problem}")

    nuts = config.get("nuts")
    if not isinstance(nuts, list):
        errors.append("nuts: must be a list")
        return errors
    seen: set[str] = set()
    for i, nut in enumerate(nuts):
        if not isinstance(nut, dict):
            errors.append(f"nut {i + 1}: must be an object")
            continue
        key = nut.get("key")
        where = f"nut {key or i + 1}"
        if not isinstance(key, str) or not KEY_PATTERN.match(key):
            errors.append(f"{where}: key must be letters, digits and single underscores")
        elif key.upper() in seen:
            errors.append(f"{where}: key is used twice (case is ignored)")
        else:
            seen.add(key.upper())
        if nut.get("shape") != "square":
            errors.append(f"{where}: shape must be square")
        for name in ("across_flats", "thickness", "max_roof_span", "tool_reach"):
            _check_positive(errors, where, nut, name)
        feeder = nut.get("feeder")
        if not isinstance(feeder, int) or isinstance(feeder, bool) or feeder < 0:
            errors.append(f"{where}: feeder must be a whole number, zero or more")
        for cls, ranges, minimums in (
            ("flat", ("width", "depth"), ()),
            ("edge", ("thickness", "width"), ("height_min",)),
            ("corner", ("thickness", "opening"), ("height_min",)),
        ):
            spec = nut.get(cls)
            if not isinstance(spec, dict):
                errors.append(f"{where}: {cls} settings missing")
                continue
            if not isinstance(spec.get("enabled"), bool):
                errors.append(f"{where} {cls}: enabled must be true or false")
            for name in ranges:
                _check_range(errors, f"{where} {cls}", spec, name)
            for name in minimums:
                _check_positive(errors, f"{where} {cls}", spec, name)
        if isinstance(nut.get("corner"), dict):
            _check_positive(errors, f"{where} corner", nut["corner"], "seat_gap_max",
                            allow_zero=True)
    return errors


def parse(config: dict) -> Library:
    """Validate the settings and return typed objects. Raises ConfigError."""
    errors = validate(config)
    if errors:
        raise ConfigError(errors)
    s = config["settings"]
    settings = Settings(
        axis_tolerance_deg=float(s["axis_tolerance_deg"]),
        body_tolerance_mm=float(s["body_tolerance_mm"]),
        min_top_clearance_mm=float(s["min_top_clearance_mm"]),
        on_error=s["on_error"],
        firmware=s["firmware"],
        templates=dict(s["templates"]),
    )
    nuts = {}
    for n in config["nuts"]:
        f, e, c = n["flat"], n["edge"], n["corner"]
        nuts[n["key"].upper()] = NutType(
            key=n["key"],
            label=str(n.get("label", "")),
            shape=n["shape"],
            across_flats=float(n["across_flats"]),
            thickness=float(n["thickness"]),
            feeder=int(n["feeder"]),
            max_roof_span=float(n["max_roof_span"]),
            tool_reach=float(n["tool_reach"]),
            flat=FlatSpec(f["enabled"], tuple(f["width"]), tuple(f["depth"])),
            edge=EdgeSpec(e["enabled"], tuple(e["thickness"]), tuple(e["width"]),
                          float(e["height_min"])),
            corner=CornerSpec(c["enabled"], tuple(c["thickness"]), tuple(c["opening"]),
                              float(c["seat_gap_max"]), float(c["height_min"])),
        )
    return Library(settings=settings, nuts=nuts)
