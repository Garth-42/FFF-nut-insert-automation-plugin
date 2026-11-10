# Nut inserter for OrcaSlicer 2.5

An OrcaSlicer plugin for toolchanging printers that place nuts during a print.
It finds bodies named `NUT_<key>` (for example `NUT_M3SQ`), measures the pocket each
one sits in, checks the pocket against a nut library, shows a report and a preview
tab, and writes one insert command per nut into the exported G-code.

The design and the build brief are in [`docs/SPEC.md`](docs/SPEC.md).

## Status

All seven milestones of the build brief are implemented. 88 tests pass on synthetic
meshes and G-code, one real G-code file exported from OrcaSlicer, and a stand-in `orca`
module.

In OrcaSlicer 2.5.0 (macOS) the check, the docked panel, the Nuts tab, the Modifier
check and the notifications have been seen working on a real part. **The slice gate and
the export step have not**: an export made with the plugin installed contained no insert
block, and why is still being tracked down (see [`docs/api-facts.md`](docs/api-facts.md)).
Run offline on that same file, the export logic writes the block correctly.

OrcaSlicer asks for permission on every file a plugin opens, including the roughly 120
files Python reads to load numpy. The plugin therefore asks once, when it is installed,
for read access to Python's library folders. Answer Yes, then restart OrcaSlicer once.
The manual checks are in [`docs/manual-test.md`](docs/manual-test.md).

First-build limits: square nuts only, plate 1 only, print order by layer, no support
material in pockets, and you set each nut body to Modifier by hand.

## Run the tests and build

You need [uv](https://docs.astral.sh/uv/). It creates the environment for you.

```bash
uv run pytest -q
```

```bash
uv run ruff check
```

```bash
uv build
```

`uv build` writes `dist/nut_inserter-0.2.2-py3-none-any.whl`.

## Try it without Orca

Detection on STL files of one object. Name the nut body with `NAME=file`:

```bash
uv run python -m nutcore.cli check part.stl NUT_M3SQ=nut.stl --json report.json
```

The export step on a sliced G-code file. The input is not modified; the result goes to
`in.nuts.gcode` unless you pass `-o`:

```bash
uv run python -m nutcore.cli inject report.json in.gcode --firmware klipper
```

## Install into OrcaSlicer

1. Build the wheel with `uv build`.
2. In OrcaSlicer's data folder, make a folder under `orca_plugins`, for example
   `orca_plugins/nut_inserter/`, and put the `.whl` in it as its only file. The Plugins
   window also has "Install local plugin".
3. Restart OrcaSlicer. Plugin output goes to the newest `python_*.log` in the data
   folder's `log` directory.

Run the probe first (`probe/nut_api_probe.py`, installed the same way in its own
folder). It settles what Orca's documentation leaves open. See `docs/manual-test.md`.

## How you use it

1. In CAD, model each nut as its own body inside its pocket and name it `NUT_M3SQ`
   (any name containing `NUT_<key>` works: `NUT_M3SQ:1`, `Bracket/NUT_M3SQ`, ...).
2. Import the STEP file into OrcaSlicer. The plugin checks the nuts whenever the model
   changes, or when you press **Check nuts**.
3. Set every nut body to Modifier: select it in the object list, right-click,
   Change type, Modifier. A plugin cannot do this in 2.5, but it can see it: a nut body
   that still prints is reported as an error.
4. Fix anything the panel or the **Nuts** tab reports. Messages give the measurement,
   the allowed range and the change to make in CAD.
5. Slice and export. An error blocks the slice (or skips the nut, your choice). At
   export the plugin proves from the toolpath that each pocket is empty, then writes
   the insert blocks.

## What your printer macro must do

The plugin only writes the block. It looks like this (Klipper):

```
;NUT_INSERT_BEGIN layer_z=6.400 count=1
INSERT_NUT KEY=M3SQ CLASS=FLAT X=112.400 Y=87.250 Z=5.300 Z_LOW=4.400 YAW=30.00 FEEDER=1 TOOL=0
;NUT_INSERT_END
```

The block starts with the print tool at the end of its last extrusion, hot and not
retracted. Your macro (Klipper `INSERT_NUT`, RepRapFirmware `insert_nut.g`) or your
own Marlin lines must retract and park the print tool, place the nut, and bring the
print tool back to the same position, primed, with the positioning and extruder modes
unchanged.

X and Y are the pocket centre, Z is the centre of the seated nut and Z_LOW its lowest
point, in bed coordinates as printed. YAW is the yaw of the flats (flat nut) or the
heading of the thread axis (nut on edge or corner). TOOL is the print tool that was
active. Templates are editable in the panel; placeholders are listed there.

Before the first real insert, run the file once with the macro replaced by a pause.

## The numbers are placeholders

Every pocket, slot, span and reach number in the default library is a placeholder.
Replace them in the panel with values from test prints with your own nuts and printer.

## Layout

```
src/nutcore/        detection, checker, report, G-code export. Plain Python + numpy.
src/nut_inserter/   the Orca plugin. adapter.py holds every orca.host call.
probe/              single-file plugin that logs what Orca's plugin API exposes
tests/              builders.py (synthetic meshes and G-code), fake_orca/, test_*.py
docs/               SPEC, DECISIONS (deviations), api-facts, api-gaps, manual-test
```

The data flow:

```
Orca model --(nut_inserter.adapter)--> ModelSnapshot
ModelSnapshot + settings --(nutcore.pipeline.detect)--> Report
Report --> panel summary, Nuts tab, slice gate, export step
export step: Report + G-code file --(nutcore.gcode)--> G-code with insert blocks
```
