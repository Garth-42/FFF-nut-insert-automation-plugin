"""Bring-up files for the heat-set tool: its whole routine in the air, in rehearse mode.

    uv run python -m heatsetcore.bringup --x 150 --y 150 [--z 40] [--firmware klipper]
        [--settings nut_settings.json] [--key M3x5.7] [--out air_test.gcode]

One insert's routine at X, Y, its surface taken Z above the bed, where nothing is: the tool
change, every move and every heat-set command, with no heat, no follower move and no probe,
because the file is always in rehearse mode. In rehearse mode the pad stays probe_start or
more above Z. Run it on a homed printer with the bed clear, the first time with a hand near
the emergency stop.

--settings takes the JSON the Nut panel's Export button shows, so the routine uses your
profile: tool number, pad offset, heights and speeds. Without it, the default profile. The
firmware is the profile's unless --firmware says otherwise.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from nutcore import __version__, library

from . import emit, profile, routine

MIN_Z = 5.0     # mm: the air test's surface at least this far above the bed


def air_test(prof: dict, x: float, y: float, z: float = 40.0, version: str = __version__) -> str:
    """The G-code of one insert's routine at (x, y), surface z, in rehearse mode."""
    if z < MIN_Z:
        raise ValueError(f"Z {z:g} is too low for an air test: use {MIN_Z:g} mm or more")
    p = {**prof, "mode": "rehearse"}
    problems = profile.validate_profile(p)
    if problems:
        raise ValueError("; ".join(problems))
    temp, _ = profile.insert_temperature(p, None, "PLA")          # rehearse never heats
    block = emit.Block(1, "end_of_print", routine.z_safe(p, z),
                       (emit.Insert("air test", x, y, z),))
    lines = [f"; Heat-set air test: one insert's routine at X{emit.length(x)} "
             f"Y{emit.length(y)}, surface Z{emit.length(z)}, in rehearse mode.",
             "; No heat, no follower move, no probe. Home the printer and clear the bed first."]
    if p["firmware"] == "reprapfirmware":
        lines += ["if !move.axes[0].homed || !move.axes[1].homed || !move.axes[2].homed",
                  '  abort "Heat-set air test: home X, Y and Z first"']
    lines += emit.header_lines(p, 1, temp, version, "air test")
    lines.append(emit.preheat_line(p, temp))
    lines += emit.block_lines(p, block, temp)
    return "\n".join(lines) + "\n"


def profile_from(settings: str | None, key: str | None) -> dict:
    """The heat-set profile to use: from the panel's exported settings, or the default."""
    if not settings:
        return profile.default_profile()
    config = library.migrate(json.loads(Path(settings).read_text(encoding="utf-8")))
    errors = library.validate(config)
    if errors:
        raise ValueError("the settings are not usable: " + " ".join(errors))
    profiles = config["heatset"]["profiles"]
    if not profiles:
        raise ValueError("the settings hold no heat-set profile")
    if key is None:
        return profiles[0]
    found = profile.profile_for_key(profiles, key)
    if found is None:
        keys = ", ".join(p["insert_key"] for p in profiles)
        raise ValueError(f"no heat-set profile has key {key}; the settings have {keys}")
    return found


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="heatsetcore.bringup",
                                     description=__doc__.splitlines()[0])
    parser.add_argument("--x", type=float, required=True, help="the insert's X, mm")
    parser.add_argument("--y", type=float, required=True, help="the insert's Y, mm")
    parser.add_argument("--z", type=float, default=40.0,
                        help=f"the surface's height above the bed, mm (default 40, at least "
                             f"{MIN_Z:g})")
    parser.add_argument("--firmware", choices=profile.FIRMWARES,
                        help="the profile's firmware when left out")
    parser.add_argument("--settings", help="settings JSON from the Nut panel's Export button")
    parser.add_argument("--key", help="the heat-set profile's insert key; the first when left out")
    parser.add_argument("--out", help="the G-code file to write; the console when left out")
    args = parser.parse_args(argv)
    try:
        prof = profile_from(args.settings, args.key)
        if args.firmware:
            prof = {**prof, "firmware": args.firmware}
        text = air_test(prof, args.x, args.y, args.z)
    except (ValueError, OSError) as exc:
        print(f"heatsetcore.bringup: {exc}", file=sys.stderr)
        return 2
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"Wrote {args.out}: {prof['firmware']}, rehearse mode, X{args.x:g} Y{args.y:g} "
              f"Z{args.z:g}")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
