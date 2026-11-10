"""Firmware templates for the insert block.

A template is text with {placeholders}. Values are filled in as ready-made
strings: lengths with 3 decimals, angles with 2, never in exponent form.
"""

from __future__ import annotations

PLACEHOLDERS = ("index", "key", "cls", "x", "y", "z", "z_low", "z_high", "yaw", "feeder",
                "layer_z", "tool", "rx", "ry", "rz")


class TemplateError(ValueError):
    """A template cannot be used. Reported as E_TEMPLATE."""


def fmt_length(value: float) -> str:
    text = f"{value:.3f}"
    return "0.000" if text == "-0.000" else text


def fmt_angle(value: float) -> str:
    text = f"{value:.2f}"
    return "0.00" if text == "-0.00" else text


def check_template(text: str) -> str | None:
    """Return what is wrong with a template, or None when it renders."""
    dummy = dict.fromkeys(PLACEHOLDERS, "0")
    try:
        text.format_map(dummy)
    except KeyError as exc:
        return f"unknown placeholder {{{exc.args[0]}}}. Known: " + ", ".join(
            "{" + p + "}" for p in PLACEHOLDERS)
    except (ValueError, IndexError) as exc:
        return f"cannot be rendered ({exc}). Write a literal brace as {{{{ or }}}}"
    return None


def render(template: str, values: dict) -> list[str]:
    """Fill a template and return its lines. Raises TemplateError."""
    problem = check_template(template)
    if problem:
        raise TemplateError(problem)
    return template.format_map(values).splitlines()


def pick_firmware(setting: str, flavor: str | None) -> str:
    """Choose the firmware name from the setting, or from Orca's G-code flavor when auto."""
    if setting != "auto":
        return setting
    text = (flavor or "").lower()
    for needle, name in (("klipper", "klipper"), ("reprap", "reprapfirmware"),
                         ("marlin", "marlin")):
        if needle in text:
            return name
    raise TemplateError(
        f"cannot tell the firmware from the G-code flavor {flavor!r}. "
        "Pick Klipper, RepRapFirmware or Marlin in the Nut panel")


def firmware_template(templates: dict, firmware: str) -> str:
    """The template text for a firmware. Raises TemplateError when it is empty."""
    text = templates.get(firmware, "")
    if not text.strip():
        if firmware == "marlin":
            raise TemplateError(
                "Marlin needs your own insert lines: Marlin macros take no parameters, "
                "so write the lines in the Nut panel's Marlin template")
        raise TemplateError(f"the {firmware} template is empty")
    return text
