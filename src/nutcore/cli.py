"""Desk testing without Orca.

    python -m nutcore.cli check part.stl NUT_M3SQ=nut.stl
    python -m nutcore.cli inject report.json in.gcode --firmware klipper
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

from . import library
from .gcode.inject import FAILURE, inject
from .mesh import InstanceSnapshot, ObjectSnapshot, PartSnapshot, make_snapshot, read_stl
from .pipeline import detect
from .report import Report


def _load_config(path: str | None) -> dict:
    if not path:
        return library.default_config()
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _check(args) -> int:
    parts = []
    for item in args.parts:
        name, _, path = item.rpartition("=")
        path = Path(path)
        mesh = read_stl(path)
        parts.append(PartSnapshot(name=name or path.stem, vertices=mesh.vertices,
                                  triangles=mesh.triangles, matrix=np.eye(4)))
    snapshot = make_snapshot([ObjectSnapshot(
        parts=tuple(parts), instances=(InstanceSnapshot(matrix=np.eye(4), mirrored=False),))])
    report = detect(snapshot, _load_config(args.config))

    for nut in report.nuts:
        where = "no placement"
        if nut.placement:
            where = "X {:.3f} Y {:.3f} Z {:.3f}".format(*nut.placement)
        print(f"#{nut.index} {nut.name}: {nut.cls or '-'} {nut.status.upper()}, {where}")
        for f in nut.findings:
            print(f"    {f.level} {f.code}: {f.message}")
    s = report.summary
    print(f"{len(report.nuts)} nut(s): {s['ok']} ok, {s['warning']} warning, {s['error']} error")
    if args.json:
        Path(args.json).write_text(report.to_json(), encoding="utf-8")
    if args.csv:
        Path(args.csv).write_text(report.to_csv(), encoding="utf-8")
    return 1 if s["error"] else 0


def _inject(args) -> int:
    config = _load_config(args.config)
    if args.firmware:
        config["settings"]["firmware"] = args.firmware
    if args.on_error:
        config["settings"]["on_error"] = args.on_error
    lib = library.parse(config)
    report = Report.from_json(Path(args.report).read_text(encoding="utf-8"))
    source = Path(args.gcode)
    text = source.read_bytes().decode("utf-8", "surrogateescape")
    result = inject(text, report, lib, flavor=args.flavor)
    print(f"{result.status}: {result.message}")
    for nut in result.report.nuts:
        print(f"#{nut.index} {nut.name}: export {nut.export}")
    if result.changed:
        target = Path(args.output) if args.output else source.with_suffix(".nuts.gcode")
        target.write_bytes(result.text.encode("utf-8", "surrogateescape"))
        print(f"written to {target}")
    return 1 if result.status == FAILURE else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="nutcore", description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)

    check = commands.add_parser("check", help="run nut detection on STL files of one object")
    check.add_argument("parts", nargs="+", metavar="[NAME=]file.stl",
                       help="a part; name nut bodies like NUT_M3SQ=nut.stl")
    check.add_argument("--config", help="settings JSON; the defaults when left out")
    check.add_argument("--json", help="write the report as JSON to this file")
    check.add_argument("--csv", help="write the report as CSV to this file")
    check.set_defaults(run=_check)

    inj = commands.add_parser("inject", help="write insert blocks into a G-code file")
    inj.add_argument("report", help="report JSON from the check command")
    inj.add_argument("gcode", help="sliced G-code file; it is not modified")
    inj.add_argument("--firmware", choices=library.FIRMWARES)
    inj.add_argument("--flavor", help="G-code flavor text, used when firmware is auto")
    inj.add_argument("--on-error", choices=("block", "skip"))
    inj.add_argument("--config", help="settings JSON; the defaults when left out")
    inj.add_argument("-o", "--output", help="output file; default <name>.nuts.gcode")
    inj.set_defaults(run=_inject)

    args = parser.parse_args(argv)
    return args.run(args)


if __name__ == "__main__":
    sys.exit(main())
