# Nut insertion plugin for OrcaSlicer 2.5: architecture

Nov 10, 2026 · @Garth

## Summary

The plugin finds `NUT_…` bodies, measures each pocket, classifies orientation, checks tolerances, and shows a report and a preview tab, all inside OrcaSlicer 2.5. This doc is also the build brief for Claude Code: the sections up to Export describe the design, and the sections titled "Build brief" say exactly what to make and how to prove it.

- **STEP in the Design tab: not the better route.** A plugin only sees triangle meshes. For flat-sided nuts and pockets, the mesh gives the same centre, size and angle as the STEP solid. Detection runs on the mesh in Prepare.
- **Set to Modifier: not possible from a plugin yet.** The model is read-only to plugins. You change the type by hand after import, and the plugin refuses to export if a nut body would still print.
- **Everything else is supported:** name matching, pocket centre, orientation classes with a warning for unsupported ones, a library panel, a tolerance checker with fix-in-CAD messages, a report, and a Nuts tab with highlighted boxes and centroids.

Decisions confirmed on 10 Nov 2026:

- Body names survive STEP import into Orca.
- An on-edge nut may stand on a flat or on a corner.
- Insert commands are written for Klipper, RepRapFirmware and Marlin.
- Fusion 360 is the reference CAD. Name matching is tolerant enough for other CAD, and a nut can always be named by hand.

## What the OrcaSlicer 2.5 plugin API allows

Two steps you asked for are outside what a 2.5 plugin can do: changing a part to a modifier, and reading Design-tab solids. The rest maps onto documented plugin features.

| Need | In 2.5 | How |
| --- | --- | --- |
| Find parts named `NUT_…` | Yes | Part names are readable |
| Measure nut and pocket | Yes | Each part's triangle mesh is readable as numpy arrays, in mm |
| Bed position and rotation of each copy | Yes | Part and instance transform matrices |
| Set a nut body to Modifier | No | The model is read-only to plugins |
| Tell whether a body is already a modifier | No | Part type is not in the documented API |
| Read STEP or Design-tab solids | No | Only meshes are exposed |
| Nut library panel | Yes | Docked HTML panel on Prepare and Preview; a plugin can save its own settings |
| Report and preview | Yes | A plugin tab beside Prepare and Preview: an HTML page with a message bridge to Python |
| Draw in Orca's own 3D view, or read the selection | No | Not in the documented API |
| Re-check when the model changes | Yes | Lifecycle events for objects added, changed and transformed |
| Stop a slice on an error | Yes | A failure returned by a slicing step is raised as a slicing error |
| Write insert commands | Yes | A final post-processing step edits the exported G-code |
| Know which plate is being exported | No | Not in the documented API; the export step checks positions against the G-code instead |

Orca describes the plugin API as new and still subject to change, so every `orca.*` call sits in one small plugin package. Details are in the [host API](https://github.com/OrcaSlicer/OrcaSlicer/wiki/host), [plugin development guide](https://github.com/OrcaSlicer/OrcaSlicer/wiki/plugin_development) and [slicing pipeline](https://github.com/OrcaSlicer/OrcaSlicer/wiki/slicing) pages.

## STEP in the Design tab vs mesh in Prepare

Working on STEP solids would not make nut placement more accurate, would make the algorithm only slightly simpler, and is not possible from a 2.5 plugin. The design measures the mesh in Prepare.

**Availability.** The [Design tab](https://www.orcaslicer.com/wiki/design/design_tab.html) imports STEP as a real solid and hands it to Prepare with Commit to Plate. The plugin API then exposes that part only as a triangle mesh. Nothing documented lets a plugin read Design-tab bodies or faces.

**Accuracy.** A square nut and a square pocket are bounded by flat faces, and a flat face tessellates exactly: its mesh vertices are the CAD corner points. Centre, size and angle computed from them match the STEP values to well under a micron. Only curved faces (the bolt hole, fillets) carry a chord error, set by the linear deflection chosen in the [STEP import dialog](https://www.orcaslicer.com/wiki/general_settings/import_export), and no placement number depends on them. The limit on placement is the printer and its tool offsets, not the geometry source.

**Ease.** Solids would hand over faces, their types and exact axes directly. On a mesh the same faces come back by grouping triangles that share a plane, a few dozen lines of numpy, and from there the algorithm is identical. Solids start to pay off for shapes with curved walls, such as round inserts or hex nuts in filleted pockets.

**Cost of forcing it.** Reading the STEP file from the plugin means shipping a CAD kernel as a dependency, finding the source file (its path is not exposed), and re-aligning its coordinates with Orca's part, which is moved on import. It would also miss anything done in Prepare: rotation, scaling, cuts.

**Decision.** Measure the mesh, behind a small geometry interface that returns flat faces. If Orca later exposes solids to plugins, a second implementation slots in and nothing above it changes.

## Architecture

*(Architecture diagram: in the Markdown export it is replaced by the data flow block under "Build brief: repository layout and tooling".)*

Only the adapter and the three outputs touch Orca. The core is ordinary Python that can be tested at a desk on STL files and reused from a command line.

| Module | Job | Orca feature used |
| --- | --- | --- |
| `nut_inserter.adapter` | Turns the live model into plain arrays; the only place that reads Orca's model | Host API |
| `nutcore.library` | Settings: nut entries, defaults, validation | Plugin settings |
| `nutcore.naming`, `faces`, `frame`, `rays`, `pocket` | The detection steps | None |
| `nutcore.checker` | Compares measurements with the library and builds findings | None |
| `nutcore.report` | Records, JSON and CSV | None |
| `nutcore.gcode` | G-code parser, pocket proof, firmware templates, insertion | None |
| `nut_inserter.state` | Cached report and stale flag, shared by the capabilities | None |
| `nut_inserter.ui_panel` | Library editor and check summary | Docked panel |
| `nut_inserter.ui_preview` | The Nuts tab | Pages |
| `nut_inserter` capabilities | Check nuts action, model-change handling, slice gate, export step | Script, lifecycle events, slicing pipeline |

Threads shape two choices. Model-change events normally arrive on the UI thread and handlers must return quickly, so the check runs there only while it stays fast and otherwise marks the report stale. Slicing steps run on a worker thread, where reading the model is not documented as safe. So the gate and the export step both use the report cached on the UI thread, and a stale report blocks the slice until the check has run.

The plugin ships as one wheel with numpy as its only dependency. Orca installs plugin dependencies itself.

## Nut library and panel

The library is one list of nut types. Each entry ties a name key to the nut's size and to the pocket geometry you have proven with test prints.

The panel docks beside the sidebar on Prepare and Preview. It shows the library as an editable table with add, duplicate, delete, import and export (JSON). Each entry has these fields:

| Field | Example for `M3SQ` | Meaning |
| --- | --- | --- |
| Key | `M3SQ` | Bodies named `NUT_M3SQ` use this entry |
| Shape | Square | Square only for now |
| Width across flats | 5.5 mm | Nominal nut size |
| Thickness | 1.8 mm | Nominal nut size |
| Classes enabled | Flat, edge, corner | Which orientation classes the tool can place |
| Flat pocket width | 5.70–5.90 mm | Min–max, both directions across the flats |
| Flat pocket depth | 2.00–2.60 mm | Min–max from floor to roof or rim |
| Slot thickness | 2.00–2.30 mm | Edge and corner: min–max along the thread axis |
| Edge slot width | 5.70–5.90 mm | Min–max across the flats, horizontal |
| Edge slot height | 5.70 mm or more | Minimum from floor to roof or rim |
| Corner slot opening | 7.98–8.18 mm | Min–max horizontal width beside the nut's side corners |
| Corner seat gap | 0–0.20 mm | Allowed gap between each lower flat and its wall |
| Corner slot height | 7.98 mm or more | Minimum from the nut's lowest corner to roof or rim |
| Max roof span | 6 mm | Longest bridge your printer closes over the nut |
| Tool reach | 3 mm | How far below the current layer the tool can seat a nut |
| Feeder | 1 | Passed to the printer macro |

Every pocket, slot, span and reach number above is a placeholder. Replace them with values from your own test prints; they are the only tuning the plugin needs.

The same panel holds the general settings: the angle window, whether an error blocks the slice, the firmware, and the insert templates.

Storage uses the plugin's own settings, which a plugin can read and save. That gives two things for free. The same library is editable as JSON in the Plugins window's Config tab, and Orca's per-preset overrides let a printer or filament preset carry different pocket ranges. The exported JSON can also drive your CAD template, so the design guideline and the checker read the same numbers.

## Detection pipeline

Detection is one pure function: a snapshot of the model plus the nut library go in, one record per nut comes out. It stores nothing in the project. The nut bodies in the model are the record, so copies, moves and saved projects keep working.

It runs when you click Check nuts and whenever an object is added, changed, renamed or transformed, so the report is current when you slice.

1. **Snapshot.** Read every object's parts: name, mesh and transforms. Put each part's vertices into bed coordinates for each copy on the plate. All measuring happens there, in millimetres as printed, so a scaled object fails the size checks on its own.
2. **Match names.** A part is a nut when its name contains `NUT_` followed by a library key, for example `NUT_M3SQ`. Matching ignores case. It needs the start of the name or a character that is not a letter or digit before `NUT_`, and the end of the name or such a character after the key. The longest key that fits wins. So `NUT_M3SQ`, `NUT_M3SQ:1`, `NUT_M3SQ v2:1`, `NUT_M3SQ (2)`, `nut_m3sq-3` and `Bracket/NUT_M3SQ` all match, and `DONUT_M3SQ` does not. A `NUT_` name with no library entry is an error, not a silent skip. If a CAD export mangles a name, name the body by hand in CAD or rename the part in Orca.
3. **Flat faces.** Group each mesh's triangles into flat faces by normal and plane offset. A square nut and its pocket are made of flat faces, so this recovers the CAD faces exactly.
4. **Nut frame.** From the nut body's faces take three perpendicular axes and the body's extent along each. The extent that matches the library thickness marks the thread axis, and the other two must match the width across flats. A body that doesn't measure like its name is an error (a `NUT_M3SQ` that measures 7 × 7 × 2.2). The nut centre is the middle of the three extents.
5. **Orientation.** Classify the nut from its axes (next section).
6. **Pocket walls.** From a grid of points on each of the nut's six faces, cast rays along the face normal into the other parts of the same object. The nearest wall each face sees gives the gap on that side. Rays that fall into the bolt hole or a corner relief are outliers. They are dropped by taking the nearest distance that at least a quarter of the rays agree on.
7. **Seat.** Faces that point downward are seat faces: the bottom of a flat or edge nut, the two lower flats of a corner nut. The nut is settled onto them, moved until each seat face touches its wall. That gives the height the real nut will rest at.
8. **Sideways centre.** In each horizontal direction with a wall on both sides, pocket size = nut size + the two gaps, and the nut is centred between the walls.
9. **Drop path.** Rays cast straight up from the seated nut must be clear up to the roof. No hit at all means an open-top pocket.
10. **Placement point.** The centre of the seated, centred nut in bed coordinates. X and Y therefore come from the pocket, not the nut body, so a nut modelled slightly off-centre is still placed in the middle of the hole. The record also carries the class, the angles, the lowest and highest point of the seated nut, the roof height, and the Z window in which insertion is possible.

A negative gap means the nut body cuts into the part, and no wall within reach means there is no pocket. Both are errors.

## Orientation rules

A nut is insertable when its thread axis is parallel or perpendicular to the layer normal (Z), at any rotation about Z. Anything in between gets a warning and no insert command.

The class comes from the nut's axes in bed coordinates, after the object's rotation on the plate.

| Class | Your term | Test | Angle reported |
| --- | --- | --- | --- |
| `FLAT` | Horizontal nut | Thread axis within 0.5° of Z | Yaw of the flats about Z, 0–90° |
| `EDGE` | Vertical nut on a flat | Thread axis within 0.5° of the XY plane, one pair of flats vertical | Heading of the thread axis about Z, 0–180° |
| `CORNER` | Vertical nut on a corner | Thread axis within 0.5° of the XY plane, flats at 45° to vertical | Heading of the thread axis about Z, 0–180° |
| `TILTED` | Unsupported | Thread axis at any other angle to Z | Tilt from Z |
| `ROLLED` | Unsupported | Thread axis horizontal, flats at neither 0° nor 45° | Roll about the thread axis |

- The 0.5° window is a setting. CAD-exact parts land within thousandths of a degree, so a wider miss is a real design or placement error.
- Orientation is judged per copy on the plate. Rotating a part onto another face in Prepare can turn a valid nut into a tilted one, so the check re-runs when an object is transformed.
- Each nut type switches `FLAT`, `EDGE` and `CORNER` on or off in the library. A nut in a class its type has switched off is an error, so the tool is never asked for a move it can't make.
- `TILTED` and `ROLLED` nuts stay in the report and the preview, marked as warnings, so you can see which body caused them.

## Tolerance checker

Each measured pocket is compared with the allowed range for its nut type and orientation. Anything outside the range is an error that names the size to change in CAD.

| Check | Fails when | Level |
| --- | --- | --- |
| Body size | Nut body differs from the library nut by more than 0.05 mm (default) | Error |
| Class enabled | The nut's class is switched off for its type | Error |
| Pocket or slot width | Outside the allowed range for the nut's class | Error |
| Slot thickness | Edge and corner: outside the allowed range along the thread axis | Error |
| Depth or height | Outside the allowed range for the nut's class | Error |
| Seat | A seat face has no wall within the allowed gap | Error |
| Interference | Any gap below zero | Error |
| Drop path | Something blocks the way straight down to the seat | Error |
| Tilt or roll | Class is `TILTED` or `ROLLED` | Warning |
| Roof span | Roof bridges more than the library's maximum span | Warning |
| Reach | Seated nut sits deeper below the insert layer than the tool can reach | Warning |
| Off-centre body | Nut body more than 0.1 mm from its seated, centred position | Note |

Messages give the measurement, the range and the fix. Example: "NUT\_M3SQ #4: pocket width 6.20 mm, allowed 5.70–5.90 mm. Reduce by 0.30–0.50 mm in CAD and re-export."

A nut with an error, or one classed as tilted or rolled, gets no insert command. By default an error also blocks the slice; a setting changes that to "skip the nut and continue". Notes and the other warnings never block. Errors and warnings also raise a notification in Orca's 3D view, so they are seen without opening the Nuts tab.

## Modifier handling

The plugin cannot switch a nut body to Modifier in 2.5, so that step stays manual for now and the plugin makes it hard to get wrong.

It matters because a nut body left as a normal part is printed as plastic and fills its own pocket.

- **Prompt.** After each check, the panel lists the nut bodies it found and the one manual step: select them in the object list, right-click, Change type, Modifier. As modifiers they print nothing, travel with the object when it is moved or copied, and are saved in the project.
- **Gate at export.** Part type can't be read either, so the plugin proves it from the toolpath. For every nut it looks at the G-code layers that cross the pocket: there must be extrusion around the pocket and none inside it. Plastic inside a pocket fails the export with the nut's name and the fix.
- **Later.** Reading and setting a part's type is a small, well-scoped request for the Orca plugin API, which is still open to change. The adapter module has one function for it, so the manual step disappears when the call exists and nothing else changes.

One more option is worth a prototype. Orca's slicing steps let a plugin edit sliced layers, so the plugin could cut each measured pocket out of the layers itself and make the part type irrelevant. The layer-editing calls are not documented yet, so this is not in the first build.

## Report and preview tab

Every check produces one report: a record per nut with its placement and findings. The same report feeds the panel summary, the preview tab, the export step and a JSON file.

| Field | Example |
| --- | --- |
| Nut | #4, `NUT_M3SQ`, object 2, copy 1 |
| Class and angle | Flat, yaw 30.0° |
| Pocket centre (bed) | X 112.400, Y 87.250, Z 5.400 |
| Placement point | X 112.400, Y 87.250, Z 5.300, lowest point at 4.400 |
| Pocket measured | 5.80 × 5.82 × 2.00 mm |
| Allowed | 5.70–5.90 wide, 2.00–2.60 deep |
| Insert window | Z 6.30 to 6.40; the layer number is filled in after slicing |
| Status | OK, or its errors, warnings and notes |

The report exports as JSON for tools and CSV for a quick look.

The preview is a plugin tab named Nuts, next to Prepare and Preview. It is an HTML page that asks Python for the current report each time it opens.

- **3D view.** The part's edges in grey, each pocket as a highlighted box, and each placement point as a crosshair with an arrow along the thread axis. Colour plus an icon mark OK, warning and error. Drag to orbit, scroll to zoom.
- **List.** The report table beside the view. Picking a row flies the camera to that nut and shows its findings; picking a box highlights its row.
- **Stale flag.** When the model changes, the tab says the report is out of date and re-runs the check.

A plugin cannot draw in Orca's own 3D view, so the page draws its own. It is a wireframe on a 2D canvas, which needs no WebGL and no libraries. Plugin pages are plain HTML, and whether WebGL works in them is not documented. Only edges are sent to the page, so large models stay light.

## Export

At export the plugin takes the current report, proves each pocket in the toolpath, and writes one insert block per nut at the right layer, in the syntax of the printer's firmware.

This runs as the final post-processing step on the exported G-code, after any classic post-processing scripts.

1. **Use the current report.** The check re-runs on every model change, so the cached report matches the plate as sliced. A stale report fails the export instead of guessing.
2. **Find the layers.** Read each layer's bottom and top height from the heights of the extrusion moves around the pocket. Variable layer height is handled, and nothing depends on slicer comment lines. A layer is open at a pocket when its middle height lies between the pocket floor and roof.
3. **Snap to the print.** The printed floor is the bottom of the first open layer and the printed roof is the top of the last one. Seat height and clearances are recomputed from these, because the printed pocket can differ from the model by up to half a layer.
4. **Prove each pocket.** In the open layers, require extrusion around the pocket and none inside it. This one test catches a nut body still set to print, support material in the pocket, an object moved after slicing, and a wrong plate offset. An object that is not on this plate is skipped.
5. **Pick the insert layer.** For a roofed pocket, the last open layer. For an open-top pocket, the first layer whose top clears the seated nut.
6. **Write the block.** Add it after the last move of that layer, before the next layer starts. Nuts due at the same layer are written together so they can share one tool visit.

Each firmware gets its own default block. The firmware is taken from the printer profile's G-code flavor and can be overridden in the panel. Every block is a template, so parameter names and extra lines can change without touching code.

**Klipper** calls a `gcode_macro` named `INSERT_NUT` and passes the values as named parameters:

```
INSERT_NUT KEY=M3SQ CLASS=FLAT X=112.400 Y=87.250 Z=5.300 Z_LOW=4.400 YAW=30.00 FEEDER=1 TOOL=0
```

**RepRapFirmware** calls the macro file `insert_nut.g`, which reads `param.X` and so on. The value letters avoid G, M, N and T, which are risky in macro calls, and P, which names the file:

```
M98 P"insert_nut.g" K"M3SQ" C"FLAT" X112.400 Y87.250 Z5.300 L4.400 A30.00 F1 S0
```

**Marlin** has stored macros (M810 to M819), but they take no parameters. So for Marlin the plugin writes out lines you compose once in the panel, with the values filled in:

```
; your change to the nut tool
G0 X{x} Y{y} F9000
; your place sequence, using {z} and {yaw}
; your change back to T{tool}
```

X and Y are the pocket centre, Z is the centre of the seated nut and Z\_LOW its lowest point, all in bed coordinates as printed. YAW is the angle from the orientation table. TOOL is the print tool that was active, so the macro can hand back to it.

The plugin only writes the block. Tool pickup, feeding, placing, the seat check, the return to the print tool and re-priming live in the macro or in your Marlin lines, so the same G-code keeps working as the hardware changes.

A summary at the top of the file lists every nut and its layer, and each block sits between `;NUT_INSERT_BEGIN` and `;NUT_INSERT_END` lines. A file that already has those lines is left alone, because Orca may run this step once for the file and again for an upload.

Two limits in the first build: print order must be by layer, not by object, and pockets must be free of support material.

## Open tests and risks

Your answers settled the earlier questions: names survive import, corner-standing nuts are allowed, all three firmwares are supported, and Fusion 360 is the reference CAD.

Four things still need a test in Orca, because the documentation is silent. The probe plugin in milestone 0 collects all four, and none of them blocks the core detection work.

- [ ] Model access from the slicing thread. Find out whether a slicing step may read the model. If it may, the export step can measure again instead of trusting the cached report.
- [ ] Plate offset. Find out how bed coordinates map to G-code coordinates on plates after the first. Until then the plugin supports plate 1 and writes no commands when the pocket proof fails.
- [ ] A real G-code file. Export one sliced part with a nut pocket from your printer profile, so the parser and the pocket proof are tested on Orca's own output.
- [ ] Setting names. Confirm the keys a slicing step reads for G-code flavor and print order.

Risks:

- Orca says the plugin API may still change. One small plugin package contains that risk.
- Any part not named `NUT_…` is treated as printed geometry, because part type is not readable. A non-nut modifier that overlaps a pocket would be measured as a wall.
- Real nuts vary. DIN 562 allows an M3 square nut to be 5.2–5.5 mm across flats and 1.4–1.8 mm thick, so pocket ranges should come from test prints with your own nuts.
- A corner-standing nut rests in a V of printed layers, which are stepped. Expect to tune the corner seat gap by test print more than the other ranges.

## Build brief: scope and rules

From here on the doc is written for Claude Code, starting in an empty git repository with this doc saved as `docs/SPEC.md`. Build a Python package and an OrcaSlicer 2.5 plugin wheel that implement the design above.

You will not have OrcaSlicer in your environment. Everything is proven with tests on synthetic meshes, synthetic G-code and a stand-in `orca` module. A person runs the checks that need Orca and brings the results back.

Scope of the first build:

- Square nuts only. The default library ships the single M3SQ entry with placeholder ranges. Classes `FLAT` and `EDGE` first; `CORNER` arrives in milestone 6.
- Plate 1 only, print order by layer, no support material in pockets.
- The Modifier step stays manual. The plugin detects, reports, previews, gates the slice and writes insert blocks.

Rules:

1. Only the `nut_inserter` package may import `orca`. The `nutcore` package is plain Python 3.12 and numpy, and its tests must pass without Orca.
2. The Orca calls in this brief were read from the documentation on 10 Nov 2026, and Orca says the API may change. Do not invent `orca` calls. If you need a call that is not listed, record it in `docs/api-gaps.md` and build the fallback this doc describes.
3. When the probe log from milestone 0 disagrees with this brief, the log wins. Record the difference in `docs/api-facts.md` and change only the plugin package.
4. Never crash the host. Every method Orca calls catches exceptions, prints the traceback, and returns a failure result or shows a notification.
5. Start no threads, open no network connections, spawn no processes, and touch no file except the G-code file handed to the export step. Each of those raises a permission prompt in Orca.
6. Keep lifecycle-event handlers and page-message handlers under 100 ms. If a check would take longer, mark the report stale instead.
7. Lengths are millimetres, angles are degrees, and coordinates are bed coordinates unless a name says otherwise. Z is up.
8. Commit after each milestone with its acceptance checks passing. Log every deviation from this doc, and the reason, in `docs/DECISIONS.md`.

## Build brief: repository layout and tooling

Two packages keep the Orca-facing code apart from the code that can be tested anywhere.

The data flow, in text because the architecture diagram does not survive a Markdown export:

```
Orca model --(nut_inserter.adapter)--> ModelSnapshot
ModelSnapshot + settings --(nutcore.pipeline.detect)--> Report
    detect = match names -> nut frame -> orientation -> pocket -> checker
Report --> panel summary, Nuts tab, slice gate, export step
export step: Report + G-code file --(nutcore.gcode)--> G-code with insert blocks
```

```
pyproject.toml           distribution nut-inserter, depends on numpy
README.md                run tests, build, install into Orca
CLAUDE.md                the rules above, for later sessions
docs/SPEC.md             this doc
docs/api-facts.md        what the probe log showed
docs/api-gaps.md         calls you needed and did not have
docs/DECISIONS.md        deviations from the spec
docs/manual-test.md      the manual checks from this brief
probe/nut_api_probe.py   single-file plugin for milestone 0
src/nutcore/             no orca imports
  library.py             settings schema, defaults, validation
  naming.py              name matching
  mesh.py                Mesh type, transforms, STL reader, feature edges
  faces.py               flat-face grouping
  frame.py               nut frame and orientation class
  rays.py                vectorised ray casting
  pocket.py              walls, seat, centring, drop path
  checker.py             findings
  report.py              records, JSON, CSV
  pipeline.py            detect(snapshot, config) -> Report
  gcode/parser.py        moves, layers, state
  gcode/proof.py         pocket proof
  gcode/templates.py     firmware templates
  gcode/inject.py        insert layer, blocks, summary
  cli.py                 check and inject commands for desk testing
src/nut_inserter/        the Orca plugin, the wheel's entry package
  __init__.py            capability classes and the @orca.plugin class
  adapter.py             model snapshot, settings, panel and notification calls
  state.py               cached report shared by the capabilities
  ui_panel.py            PANEL_HTML string
  ui_preview.py          PREVIEW_HTML string
tests/
  builders.py            synthetic meshes and G-code
  fake_orca/orca/        stand-in orca module for plugin-layer tests
  test_*.py
```

Tooling: Python 3.12, `uv` for the environment, `hatchling` as the build backend, `pytest` and `ruff` as dev dependencies.

- `uv run pytest -q` runs the tests.
- `uv run ruff check` lints.
- `uv build` produces `dist/nut_inserter-<version>-py3-none-any.whl`.
- `uv run python -m nutcore.cli check part.stl NUT_M3SQ=nut.stl` runs detection on STL files.
- `uv run python -m nutcore.cli inject report.json in.gcode --firmware klipper` runs the export step on a real G-code file.

Orca picks a wheel's entry package from `Import-Name` in the metadata, then from `top_level.txt` if it names one package, then from the normalised distribution name. Name the distribution `nut-inserter` so the last rule lands on `nut_inserter`. The wheel must be pure Python, with numpy declared as its dependency.

Keep the two HTML pages as Python string constants: self-contained, inline CSS and JavaScript, no external files or scripts. Orca's docs do not say how a plugin reads its own data files.

## Build brief: Orca plugin API contract

These are the only Orca calls the design uses. Each comes from the plugin pages listed under Sources.

| Purpose | Call | Notes |
| --- | --- | --- |
| Register | `@orca.plugin` on one class deriving `orca.base`, whose `register_capabilities(self)` calls `orca.register_capability(cls)` | One plugin class per file, built with no arguments |
| Script action | `orca.script.ScriptPluginCapabilityBase`: `get_name()`, `execute(self)` | UI thread. Run from the Plugins window or the Speed Dial |
| Tab | `orca.pages.PagesPluginCapabilityBase`: `get_name()`, `get_ui()` returning HTML, `on_message(data)`, `post_message(data)` | `get_ui` runs when the tab is first shown. Messages posted before that are dropped |
| Slicing step | `orca.slicing.SlicingPipelineCapabilityBase`: `get_name()`, `execute(self, ctx)` | Worker thread. Compare `ctx.step` with `orca.slicing.Step` values |
| Steps used | `orca.slicing.Step.posSlice`, `orca.slicing.Step.psGCodePostProcess` | At post-process, `ctx.gcode_path` is the file to edit, and `ctx.print` and `ctx.object` are `None` |
| Print settings | `ctx.config_value(key)` | Key names are unverified: `gcode_flavor`, `print_sequence` |
| Results | `orca.ExecutionResult.success(message="", data="")`, `.skipped(message="")`, `.failure(status, message, data="")` | `status` is `orca.PluginResult.RecoverableError` or `FatalError`. A failure from a slicing step shows as a slicing error |
| Hooks on any capability | `on_load()`, `on_unload()`, `on_lifecycle_event(self, event, ctx)` | Every enabled capability receives every event. Exceptions in handlers are swallowed |
| Events used | `orca.LifecycleEvent.ObjectAdded`, `ObjectDeleted`, `ObjectTransformed`, `ObjectChanged`, `ObjectRenamed`, `ProjectOpened`, `NewProject`, `ProjectClosed` | Handlers run on the thread that raised the event |
| Settings | `get_default_config()` returns a dict, `get_config()` returns a JSON string, `save_config(json_string)` returns a bool | Stored per capability. A preset override wins over the global value |
| Model | `orca.host.model().objects()`; object: `volumes()`, `instances()`; volume: `name`, `mesh()`, `matrix()`; instance: `matrix()`, `is_left_handed()` | Read-only. Treat as a momentary snapshot and keep no references |
| Mesh | `mesh.vertices()` is (N, 3) float32, `mesh.triangles()` is (M, 3) int32 | Part-local frame, mm, read-only arrays. Needs numpy |
| Dock panel | `orca.host.ui.create_dock_panel(html=, title=, width=, height=, on_message=, on_close=, dock="right")` | Returns a handle with `post(payload)`, `show()`, `hide()`, `is_open()`, `close()`. Create it in `on_load()` |
| Page bridge | In the page: `window.orca.postMessage(obj)` and `window.orca.onMessage(callback)` | Have each page send `ready` when it loads, and answer that |
| Notification | `orca.host.ui.push_notification(level, message)` with `orca.host.ui.NotificationLevel.WarningNotificationLevel` or `ErrorNotificationLevel` | Never call `orca.host.ui` from a slicing step: it can deadlock |
| Theme | CSS variables `--orca-bg`, `--orca-fg`, `--orca-muted`, `--orca-accent`, `--orca-accent-fg`, `--orca-border`, `--orca-font` | Injected into plugin pages |
| Logs | `print()` | Written to `data_dir()/log/python_<timestamp>_<pid>.log` |

Bed coordinates come from `M = inst.matrix() @ vol.matrix()`, a 4 × 4 float64 matrix applied to row vectors: `bed = (np.c_[v, np.ones(len(v))] @ M.T)[:, :3]`. When `inst.is_left_handed()` is true, reverse each triangle's winding.

The settings live in the slicing capability, so Orca's per-preset overrides reach the export step. The other capabilities reach them through `state.config_owner`.

The wheel's `nut_inserter/__init__.py` has this shape:

```python
import orca
from nutcore import library
from . import state
from .ui_panel import PANEL_HTML
from .ui_preview import PREVIEW_HTML

EV = orca.LifecycleEvent
MODEL_EVENTS = (EV.ObjectAdded, EV.ObjectDeleted, EV.ObjectTransformed,
                EV.ObjectChanged, EV.ObjectRenamed, EV.ProjectOpened,
                EV.NewProject, EV.ProjectClosed)


class CheckNuts(orca.script.ScriptPluginCapabilityBase):
    def get_name(self):
        return "Check nuts"

    def on_load(self):
        state.open_panel(PANEL_HTML)

    def execute(self):
        return state.guarded(state.run_check)

    def on_lifecycle_event(self, event, ctx):
        if event in MODEL_EVENTS:
            state.guarded(state.model_changed)


class NutsTab(orca.pages.PagesPluginCapabilityBase):
    def get_name(self):
        return "Nuts"

    def get_ui(self):
        return PREVIEW_HTML

    def on_message(self, data):
        state.guarded(state.on_tab_message, self, data)


class NutInsert(orca.slicing.SlicingPipelineCapabilityBase):
    def get_name(self):
        return "Nut insert"

    def get_default_config(self):
        return library.default_config()

    def on_load(self):
        state.config_owner = self

    def execute(self, ctx):
        if ctx.step == orca.slicing.Step.posSlice:
            return state.guarded(state.slice_gate)
        if ctx.step == orca.slicing.Step.psGCodePostProcess:
            return state.guarded(state.export, ctx)
        return orca.ExecutionResult.success()


@orca.plugin
class NutInserterPlugin(orca.base):
    def register_capabilities(self):
        orca.register_capability(CheckNuts)
        orca.register_capability(NutsTab)
        orca.register_capability(NutInsert)
```

`state.guarded(fn, *args)` runs `fn`, and on any exception prints the traceback and returns `orca.ExecutionResult.failure(orca.PluginResult.RecoverableError, str(exc))`.

`state` holds the cached report and these functions:

- `run_check()`: take a snapshot through the adapter, call `pipeline.detect`, cache the report, post it to the panel and the tab, and raise a notification for new errors and warnings.
- `model_changed()`: run the check if the previous one took less than `EVENT_BUDGET`. Otherwise set the stale flag and post `stale`.
- `slice_gate()` and `export(ctx)`: as the G-code contract describes, using only the cached report.
- `open_panel(html)`, `on_panel_message(data)` and `on_tab_message(tab, data)`: the page messages from the data contracts.

What the API does not offer, and the fallback this design uses:

| Missing | Fallback |
| --- | --- |
| Changing a part's type | Manual step, proven by the pocket proof at export |
| Reading a part's type | The pocket proof |
| Drawing in Orca's 3D view, reading the selection | The plugin's own tab |
| Plate information | Plate 1 only, guarded by the pocket proof |
| A documented way to read the model from a slicing step | The report cached on the UI thread |
| A documented way to stop a slice from an event handler | The slicing step at `posSlice` returns a failure |

## Build brief: data contracts

Four shapes cross module boundaries: the snapshot, the settings, the report and the page messages. Keep them stable, and version the JSON ones with `"schema": 1`.

The snapshot is built by the adapter in Orca and by `tests/builders.py` at a desk, and it is all the core ever sees of the model:

```python
@dataclass(frozen=True)
class PartSnapshot:
    name: str
    vertices: np.ndarray    # (N, 3) float64 copy, part-local, mm
    triangles: np.ndarray   # (M, 3) int32
    matrix: np.ndarray      # (4, 4) float64, part -> object

@dataclass(frozen=True)
class InstanceSnapshot:
    matrix: np.ndarray      # (4, 4) float64, object -> bed
    mirrored: bool

@dataclass(frozen=True)
class ObjectSnapshot:
    parts: tuple[PartSnapshot, ...]
    instances: tuple[InstanceSnapshot, ...]

@dataclass(frozen=True)
class ModelSnapshot:
    objects: tuple[ObjectSnapshot, ...]
    fingerprint: str        # hash of names, matrices, counts and bounds
```

The settings are one JSON document, saved with `save_config`. Ranges are `[min, max]`. The pocket numbers are the same placeholders as in the library table:

```json
{
  "schema": 1,
  "settings": {
    "axis_tolerance_deg": 0.5,
    "body_tolerance_mm": 0.05,
    "min_top_clearance_mm": 0.1,
    "on_error": "block",
    "firmware": "auto",
    "templates": {
      "klipper": "INSERT_NUT KEY={key} CLASS={cls} X={x} Y={y} Z={z} Z_LOW={z_low} YAW={yaw} FEEDER={feeder} TOOL={tool}",
      "reprapfirmware": "M98 P\"insert_nut.g\" K\"{key}\" C\"{cls}\" X{x} Y{y} Z{z} L{z_low} A{yaw} F{feeder} S{tool}",
      "marlin": ""
    }
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
      "flat": {"enabled": true, "width": [5.7, 5.9], "depth": [2.0, 2.6]},
      "edge": {"enabled": true, "thickness": [2.0, 2.3], "width": [5.7, 5.9], "height_min": 5.7},
      "corner": {"enabled": true, "thickness": [2.0, 2.3], "opening": [7.98, 8.18], "seat_gap_max": 0.2, "height_min": 7.98}
    }
  ]
}
```

`on_error` is `block` or `skip`. `firmware` is `auto`, `klipper`, `reprapfirmware` or `marlin`. A key is letters, digits and single underscores, unique without regard to case. Validation rejects a range whose minimum exceeds its maximum, and any size that is not positive.

The report is one JSON document per check. One nut record looks like this:

```json
{
  "schema": 1,
  "fingerprint": "9f2c…",
  "stale": false,
  "summary": {"ok": 5, "warning": 1, "error": 0},
  "nuts": [
    {
      "index": 4,
      "object": 2, "instance": 1, "part": 3,
      "name": "NUT_M3SQ:1", "key": "M3SQ",
      "cls": "FLAT",
      "axis": [0.0, 0.0, 1.0],
      "yaw_deg": 30.0, "tilt_deg": 0.0, "roll_deg": 0.0,
      "body_size": [5.5, 5.5, 1.8],
      "modelled_centre": [112.43, 87.25, 5.3],
      "placement": [112.4, 87.25, 5.3],
      "z_low": 4.4, "z_high": 6.2,
      "roof_z": 6.4, "rim_z": null,
      "pocket": {"width": [5.8, 5.82], "thickness": null, "depth": 2.0, "seat_gaps": [0.0]},
      "box": {"centre": [112.4, 87.25, 5.4], "axes": [[0.866, 0.5, 0.0], [-0.5, 0.866, 0.0], [0.0, 0.0, 1.0]], "half": [2.9, 2.91, 1.0]},
      "status": "ok",
      "findings": [{"code": "N_OFF_CENTRE", "level": "note", "message": "Nut body is 0.03 mm from the pocket centre."}],
      "export": null
    }
  ]
}
```

`box` is the measured pocket as an oriented box, which is what the preview draws. `export` is filled by the export step with the layer number, the layer top, and the printed `z_low` and `z_high`.

Finding codes are stable strings, so tests and the UI can rely on them:

| Level | Codes |
| --- | --- |
| Error, from the check | `E_NAME_UNKNOWN`, `E_BODY_SIZE`, `E_CLASS_DISABLED`, `E_NO_POCKET`, `E_INTERFERENCE`, `E_SEAT`, `E_WIDTH`, `E_THICKNESS`, `E_DEPTH`, `E_DROP_PATH` |
| Warning | `W_TILTED`, `W_ROLLED`, `W_ROOF_SPAN`, `W_REACH` |
| Note | `N_OFF_CENTRE`, `N_NOT_ON_PLATE` |
| Error, from the export step | `E_STALE`, `E_POCKET_NOT_EMPTY`, `E_PRINTED_DEPTH`, `E_NO_LAYERS`, `E_PRINT_ORDER`, `E_TEMPLATE` |

Pages and Python exchange JSON messages with a `type` field:

| From | Message | Meaning |
| --- | --- | --- |
| Page | `{"type": "ready"}` | The page has loaded. Reply with `config` and `report` |
| Page | `{"type": "check"}` | Run the check now |
| Page | `{"type": "save_config", "config": {}}` | Validate and save. Reply with `config` or `error` |
| Page | `{"type": "get_edges"}` | The preview asks for wireframe data |
| Python | `{"type": "config", "config": {}}` | The current settings |
| Python | `{"type": "report", "report": {}}` | The current report |
| Python | `{"type": "stale"}` | The model changed and the report is out of date |
| Python | `{"type": "edges", "segments": []}` | Feature edges of the printed parts as `[x1, y1, z1, x2, y2, z2]` rows in bed coordinates, at most 20,000 |
| Python | `{"type": "error", "message": ""}` | Shown inline in the page |

Inside Orca, exporting the report means the tab shows the JSON or CSV text to copy. The plugin writes no files; the command line tool does.

## Build brief: algorithm details and constants

Detection runs once per object, per copy and per nut part, in bed coordinates. The host is every part of the same object that is not a nut. Use numpy throughout and never loop over triangles in Python.

1. **Flat faces of the nut body.** Compute each triangle's unit normal and area, and drop triangles under 1e-9 mm². Group triangles whose normals agree within `PLANE_ANGLE_TOL` and whose plane offsets `n·p` agree within `PLANE_OFFSET_TOL`. Only nut bodies need this; the host is measured by rays.
2. **Nut frame.** Take the three largest-area face directions that are mutually perpendicular within `AXIS_TOL`. The extent along a direction is the range of the vertex projections onto it. The three extents must equal `(across_flats, across_flats, thickness)` in some order within `BODY_TOL`, else `E_BODY_SIZE`. The thickness direction is the thread axis `a`, the others are `u` and `v`, and the centre `c` is the middle of the three ranges. Fix the signs of `a`, `u`, `v` by a rule so results repeat.
3. **Class.** `tilt = acos(|a_z|)`. `FLAT` when `tilt ≤ AXIS_TOL`. On edge when `|90 − tilt| ≤ AXIS_TOL`; then `roll = acos(max(|u_z|, |v_z|))`, between 0° and 45°, gives `EDGE` for `roll ≤ AXIS_TOL`, `CORNER` for `|45 − roll| ≤ AXIS_TOL`, else `ROLLED`. Anything else is `TILTED`. Yaw is `atan2(u_y, u_x) mod 90` for `FLAT` and `atan2(a_y, a_x) mod 180` for the on-edge classes.
4. **Rays.** Möller–Trumbore, vectorised over rays and triangles, counting both sides of a triangle. First keep only host triangles with a vertex within `RAY_REACH` of `c`. For a nut face with outward normal `n` and half-extent `h` along it, the ray origins are a `RAY_GRID` × `RAY_GRID` grid over the central `RAY_INSET` of the face, pulled back to the nut's mid-plane, and the direction is `n`. Then `gap = t − h`. The face's gap is the smallest value whose `GAP_BIN` bin, with its two neighbours, holds at least `RAY_AGREE` of the rays. No such bin means that side is open. A gap below `−GAP_EPS` is `E_INTERFERENCE`.
5. **Seat.** Seat faces have `n_z ≤ −0.5`. Each must see a wall, else `E_SEAT`; for `CORNER` each gap must also be at most `seat_gap_max`. Settle the nut by solving `n_f · d = gap_f` over the seat faces for the displacement `d`. One seat face gives `d = −gap · z`. For `CORNER`, with `h = normalise(a × z)` and seat normals `(−h − z)/√2` and `(h − z)/√2` with gaps `g1` and `g2`: `d_z = −(g1 + g2)/√2` and `d_h = (g2 − g1)/√2`.
6. **Sideways.** For each opposite pair of faces with horizontal normals: `size = extent + g_plus + g_minus`, and `d += n_plus · (g_plus − g_minus)/2`. `FLAT` needs walls on all four sides and `EDGE` on both pairs, else `E_NO_POCKET` naming the open side. For `CORNER`, the thread-face pair works the same way, and the opening is measured with horizontal rays along `±h` from the nut's two side corner edges: `opening = across_flats · √2 + g_plus + g_minus`.
7. **Drop path.** From the settled nut, cast rays along `+z` from the grid points of every face with `n_z ≥ 0.5`. The roof is the robust nearest hit, as in step 4. A hit more than `GAP_BIN` below the roof, or scattered hits with no agreed roof, is `E_DROP_PATH`. No hits at all means open-top.
8. **Rim of an open-top pocket.** Walk upward from the nut's top in `RIM_STEP` steps, casting one horizontal ray per side from the nut's centre line. The rim is the last height at which every closed pair still sees both walls. Stop after 50 mm.
9. **Derived values.** The vertical half-extent `r` is `thickness/2` for `FLAT`, `across_flats/2` for `EDGE` and `across_flats/√2` for `CORNER`. `placement = c + d`, `z_low = placement_z − r`, `z_high = placement_z + r`. Depth or height is `roof_z` or `rim_z` minus `z_low`. Roof span is the smaller horizontal pocket size. The insert window runs from `z_high + min_top_clearance` up to `roof_z`. The off-centre note fires when the horizontal part of `d` exceeds `OFF_CENTRE`.
10. **Feature edges for the preview.** Weld vertices at 1e-4 mm, map each edge to its triangles, and keep edges whose two normals differ by more than 20°, plus boundary edges. Cache per part and transform per copy. Above 20,000 segments, raise the angle until they fit.

| Constant | Default | Used for |
| --- | --- | --- |
| `AXIS_TOL` | 0.5°, from settings | Class tests and perpendicularity |
| `BODY_TOL` | 0.05 mm, from settings | Nut body against library size |
| `PLANE_ANGLE_TOL` | 0.5° | Flat-face grouping |
| `PLANE_OFFSET_TOL` | 0.01 mm | Flat-face grouping |
| `RAY_GRID` | 5 | Rays per face side |
| `RAY_INSET` | 0.8 | Share of the face the grid covers |
| `RAY_REACH` | 3 × across flats | How far away a wall may be |
| `RAY_AGREE` | 0.25 | Share of rays that must agree on a wall |
| `GAP_BIN` | 0.01 mm | Histogram bin for gaps |
| `GAP_EPS` | 0.005 mm | Tolerance around a zero gap |
| `RIM_STEP` | 0.05 mm | Upward walk for open-top pockets |
| `OFF_CENTRE` | 0.1 mm | Off-centre note |
| `EVENT_BUDGET` | 100 ms | Longest check allowed inside an event handler |

## Build brief: G-code contract

The export step is plain text processing in `nutcore.gcode`. Orca drives it at `psGCodePostProcess`, and the command line drives it for testing. It never depends on slicer comment lines, because their format is unverified.

**Parser.** Read the file line by line and track:

- `G90` and `G91` positioning, `M82` and `M83` extruder mode, and `G92` resets.
- `G0` and `G1` moves with X, Y, Z and E, and `G2` and `G3` arcs in I, J form, split into straight pieces of at most `ARC_CHORD`.
- Whether a move extrudes: its E grows while X or Y changes.
- The active tool, from `T<n>` lines.

Every other line passes through untouched. Keep the file's line endings.

**Local layers.** For each nut, take the pocket's footprint rectangle in XY from the report's `box`. Its local layers are the distinct Z values of extruding moves that pass within `PROOF_RING` outside that footprint. A layer's top is its Z and its bottom is the top of the local layer below. Working per pocket keeps supports, wipe towers and other objects from confusing the layer stack.

- No such moves in the pocket's height range: the object is not on this plate. Record `N_NOT_ON_PLATE` and skip the nut.
- Extrusion that changes Z inside a move: `E_NO_LAYERS`.
- Extrusion heights that fall back by more than one layer after rising, or a print-order setting that says by object: `E_PRINT_ORDER`.

**Open layers and snapping.** A local layer is open when its middle height is above the modelled floor and below the roof. For `FLAT` and `EDGE`, the printed floor is the bottom of the first open layer, so printed `z_low` is that height and `z_high = z_low + 2r`. For `CORNER`, keep the modelled values. With a roof, the printed roof is the top of the last open layer; `E_PRINTED_DEPTH` when it is less than `min_top_clearance` above printed `z_high`.

**Pocket proof.** In every open layer, no extruding move may cross the footprint shrunk by `PROOF_INSET`. A crossing is `E_POCKET_NOT_EMPTY`, with the layer height in the message and a hint: the nut body is still a printing part, or there is support in the pocket.

**Insert layer.** With a roof: the last open layer. Open-top: the first local layer whose top is at least `z_high + min_top_clearance`. Re-check `W_REACH` with the printed values.

**Insertion point.** The line after the last extruding move in the file whose Z is at or below the insert layer's top. Collect all nuts that share a point into one block:

```
;NUT_INSERT_BEGIN layer_z=6.400 count=2
...rendered template for each nut, in report order...
;NUT_INSERT_END
```

**Templates.** Render with `str.format_map` and these placeholders. An unknown placeholder is `E_TEMPLATE`, caught when the settings are saved and again at export. Lengths print with 3 decimals and angles with 2, never in exponent form.

| Placeholder | Value |
| --- | --- |
| `{index}` | Nut number in the report |
| `{key}` | Library key, for example `M3SQ` |
| `{cls}` | `FLAT`, `EDGE` or `CORNER` |
| `{x}` `{y}` | Placement point |
| `{z}` | Centre of the seated nut, as printed |
| `{z_low}` `{z_high}` | Lowest and highest point of the seated nut |
| `{yaw}` | Yaw or heading from the orientation table |
| `{feeder}` | Feeder number from the library |
| `{layer_z}` | Top of the layer just finished |
| `{tool}` | Active print tool, or -1 if none was seen |
| `{rx}` `{ry}` `{rz}` | Nozzle position before the block |

**Firmware.** Use `settings.firmware`. When it is `auto`, read `ctx.config_value("gcode_flavor")` and choose by substring: `klipper`, `reprap` or `marlin`. No match is `E_TEMPLATE`, asking the user to pick. An empty Marlin template is `E_TEMPLATE` with the message that Marlin needs the user's own insert lines.

**What the macro must do.** State this in the README and in the panel. The block starts with the print tool at the end of its last extrusion, hot and not retracted. The macro, or the Marlin lines, must retract and park the print tool, place the nut, and bring the print tool back to the same position, primed, with the positioning and extruder modes unchanged.

**Summary and repeat runs.** Write comment lines listing each nut after the line `; HEADER_BLOCK_END` when the file has one, else at the top. If the file already contains `;NUT_INSERT_BEGIN`, return `skipped` and change nothing. On any error with `on_error` set to `block`, return a failure and leave the file untouched. With `skip`, leave out the failing nuts and add a comment line naming each.

**Slice gate.** At `posSlice`: no nuts means success. A stale report means failure with `E_STALE`. Any error with `on_error` set to `block` means failure, listing up to five nuts with their messages. It may be called once per object, so it must be cheap and give the same answer each time.

| Constant | Default | Used for |
| --- | --- | --- |
| `PROOF_RING` | 2.0 mm | Band around the footprint that defines local layers |
| `PROOF_INSET` | 0.2 mm | Shrink of the footprint for the empty-pocket test |
| `ARC_CHORD` | 0.5 mm | Longest straight piece of a split arc |
| `Z_EPS` | 0.001 mm | Equality of heights |

## Build brief: tests and fixtures

Tests build their inputs in code, so the repository needs no binary files. The one optional real input is tests/data/sample.gcode from the probe run. When it exists, a test checks that the parser finds layers around its pocket. Geometry is exact, so compare coordinates to 1e-6 mm.

Builders in `tests/builders.py`:

- `box(size, centre, rotation)`: a 12-triangle mesh.
- `nut(key, centre, rotation)`: a box of the library size named `NUT_<key>`.
- `pocket_block(...)`: a host made of separate boxes, namely a floor slab, four wall boxes and an optional roof slab. An optional square bolt hole splits the floor into four slabs. The host need not be one watertight mesh, because walls are found by rays.
- `snapshot(parts, instance_matrices)`: wraps parts in a `ModelSnapshot`.
- `gcode_ring(...)`: synthetic G-code with layers of a rectangular wall around a pocket, and options for fill inside the pocket, relative or absolute E, arcs, and layer height.

Detection cases, all with the `M3SQ` placeholder entry:

| Case | Setup | Expected |
| --- | --- | --- |
| 1 | Flat nut, pocket 5.8 × 5.8 × 2.0 with a roof | `FLAT`, ok, placement at the pocket centre, yaw 0 |
| 2 | Case 1, object rotated 30° about Z | Yaw 30.00, placement rotated with the object |
| 3 | Case 1, nut body shifted 0.15 mm in X | Placement unchanged, `N_OFF_CENTRE` |
| 4 | Pocket 6.2 wide | `E_WIDTH`, and the message contains 6.20, 5.70 and 5.90 |
| 5 | Pocket 1.9 deep | `E_DEPTH` |
| 6 | Nut body modelled 0.1 mm above the floor | ok, and `z_low` equals the floor height |
| 7 | Square bolt hole 3.4 mm through the floor | Floor still found, ok |
| 8 | Nut on edge in a slot 2.1 thick, 5.8 wide, 6.0 tall, at headings 0° and 45° | `EDGE`, ok, heading reported |
| 9 | Object tilted 20° about X | `W_TILTED`, no placement |
| 10 | On-edge nut rolled 20° about its thread axis | `W_ROLLED` |
| 11 | Instance scaled by 1.02 | `E_BODY_SIZE` |
| 12 | Part named `NUT_M4SQ` with no such key | `E_NAME_UNKNOWN` |
| 13 | Pocket 5.3 wide, narrower than the nut | `E_INTERFERENCE` |
| 14 | Nut with no host around it | `E_NO_POCKET` |
| 15 | Mirrored instance | Same result as case 1 |
| 16 | Two instances | Two records with different placements |
| 17 | Open-top pocket, 2.0 deep | ok, `roof_z` null, `rim_z` set |
| 18 | Ledge over a third of the pocket, above the nut | `E_DROP_PATH` |
| 19 | `flat.enabled` set to false | `E_CLASS_DISABLED` |
| 20 | Corner nut in a V slot (milestone 6) | `CORNER`, ok, settled as the seat formula says |

Name matching cases: `NUT_M3SQ`, `NUT_M3SQ:1`, `NUT_M3SQ v2:1`, `NUT_M3SQ (2)`, `nut_m3sq-3`, `Bracket/NUT_M3SQ` and `NUT_M3SQ.step` match `M3SQ`. `DONUT_M3SQ`, `NUT_M3SQX` and `NUTM3SQ` do not. With keys `M3SQ` and `M3SQ_THIN`, `NUT_M3SQ_THIN:1` matches the longer key.

G-code cases:

| Case | Setup | Expected |
| --- | --- | --- |
| G1 | Walls around the pocket, 0.2 mm layers, roof | Proof passes, and the block follows the last move of the last open layer |
| G2 | G1 with fill inside the pocket | `E_POCKET_NOT_EMPTY` |
| G3 | No moves near the pocket | `N_NOT_ON_PLATE`, file unchanged |
| G4 | Floor half a layer off the layer boundaries | Printed `z_low` snaps to a boundary, and `E_PRINTED_DEPTH` when the clearance is lost |
| G5 | Absolute E and relative E | Same result |
| G6 | An arc move through the pocket | `E_POCKET_NOT_EMPTY` |
| G7 | Each firmware template | Exact expected text, 3 and 2 decimals |
| G8 | Empty Marlin template | `E_TEMPLATE` |
| G9 | A file that was already processed | `skipped`, bytes identical |
| G10 | Two nuts due at the same layer | One block with `count=2` |
| G11 | Heights that fall back to a lower layer | `E_PRINT_ORDER` |

Plugin-layer tests use `tests/fake_orca`, a stand-in that implements only the calls in the API table:

- Registration registers exactly three capabilities.
- A model-change event recomputes the report, and a slow check marks it stale instead.
- A page's `ready` message is answered with `config` and `report`.
- `save_config` round-trips, and invalid settings are rejected with `error`.
- The slice gate fails on an error-level finding and passes with `on_error` set to `skip`.
- The export step edits a temporary G-code file at `psGCodePostProcess`.
- An exception inside any entry point returns a failure result and does not propagate.

## Build brief: milestones

Each milestone ends with its checks passing and a commit. Milestones 0 and 1 need nothing from Orca, so start there.

| Milestone | Build | Done when |
| --- | --- | --- |
| 0. Scaffold and probe | `pyproject.toml`, both packages, `CLAUDE.md`, README, one test, and `probe/nut_api_probe.py` | `uv run pytest` passes, `uv build` makes a wheel, and the probe is one file a person can install |
| 1. Core detection | `library`, `naming`, `mesh`, `faces`, `frame`, `rays`, `pocket`, `checker`, `report`, `pipeline`, and the `check` command | Detection cases 1 to 19 and the naming cases pass |
| 2. Plugin shell | The fake `orca`, `adapter`, `state`, the three capabilities, notifications, the slice gate | Plugin-layer tests pass, then manual check A |
| 3. Panel | `PANEL_HTML`: library table editor, settings, check summary, Modifier reminder | Message tests pass, then manual check B |
| 4. Preview tab | `PREVIEW_HTML`: canvas wireframe, pocket boxes, crosshairs, list, stale flag | Manual check C |
| 5. Export | The `gcode` package, the `inject` command, the export step | G-code cases pass, then manual check D |
| 6. Corner class | Corner seat, opening and checks | Case 20 passes, then a manual check with a V-slot part |

The probe settles what the documentation leaves open. It is a single `.py` plugin with the PEP 723 header, it changes nothing, and it prints lines prefixed `NUTPROBE`:

- `dir()` of `orca`, `orca.host`, `orca.host.ui`, `orca.slicing.Step` and `orca.LifecycleEvent`.
- For every object: `dir()` of the object, its first volume, first instance and mesh, then each volume's name, vertex and triangle counts, array dtypes and both matrices.
- Every lifecycle event, with its context fields and the thread name.
- From a slicing capability: each `ctx.step` seen, `dir(ctx)`, the thread name, whether `orca.host.model()` can be read there (inside try and except), and `ctx.config_value` for `gcode_flavor`, `print_sequence`, `printable_area` and `layer_height`.
- At `psGCodePostProcess`: the first 60 lines of the G-code file and the lines around the first two layer changes.

A person runs it once and commits the log as `docs/probe-log.txt`. Fill `docs/api-facts.md` from it and settle the open tests before milestone 2. If the log shows a readable or settable part type, record it: the manual Modifier step can then go.

## Build brief: manual checks in Orca

These are the steps only a person with OrcaSlicer can do. Copy them into `docs/manual-test.md` and keep the results in the repository.

To install a plugin, give it its own folder under `orca_plugins` in OrcaSlicer's data folder, holding exactly one entry file: the `.py` or the `.whl`. The Plugins window also has Install local plugin. Restart Orca after replacing a file. Plugin output goes to the newest `python_*.log` in the data folder's `log` directory.

A single-file plugin starts with this header:

```python
# /// script
# requires-python = ">=3.12"
# dependencies = ["numpy"]
#
# [tool.orcaslicer.plugin]
# name = "Nut API probe"
# description = "Prints what the plugin API exposes. Changes nothing."
# author = "nut-inserter"
# version = "0.1.0"
# ///
```

- [ ] Probe. Install `probe/nut_api_probe.py`. Open a project with a two-body STEP, a part plus `NUT_M3SQ`. Move the object, slice, and export G-code. Save the newest Python log as `docs/probe-log.txt`, and the exported file as `tests/data/sample.gcode`.
- [ ] A, Check nuts. Install the wheel and run Check nuts from the Plugins window. Expect a result line with the nut count. Rotate the part 20° about X and expect a warning notification.
- [ ] B, Panel. Narrow the flat pocket width range until the test part fails, save, and see the error state the measured width. Restart Orca and confirm the change was kept.
- [ ] C, Preview. Open the Nuts tab and find the part's edges, one box per pocket, and a crosshair at each placement point. Move the part in Prepare and confirm the tab follows.
- [ ] D, Export. With the nut body still a normal part, export and expect a slicing error naming the nut. Set it to Modifier, export again, and find one insert block after the last layer below the pocket roof, in your firmware's syntax.
- [ ] E, Dry run. On the printer, run the file once with the insert macro replaced by a pause, before the first real insert.

## Sources

All read on 10 Nov 2026.

- OrcaSlicer plugin API reference: [registry](https://www.orcaslicer.com/wiki/developer_reference/plugin_development/api_reference/registry.html), [host](https://www.orcaslicer.com/wiki/developer_reference/plugin_development/api_reference/host.html), [host UI](https://www.orcaslicer.com/wiki/developer_reference/plugin_development/api_reference/host_ui.html), [slicing pipeline](https://www.orcaslicer.com/wiki/developer_reference/plugin_development/api_reference/slicing.html), [pages](https://github.com/OrcaSlicer/OrcaSlicer/wiki/pages), [lifecycle events](https://github.com/OrcaSlicer/OrcaSlicer/wiki/lifecycle_events)
- [OrcaSlicer plugin development guide](https://www.orcaslicer.com/wiki/developer_reference/plugin_development/plugin_development.html)
- [OrcaSlicer 2.5.0 alpha release notes](https://www.orcaslicer.com/wiki/releases/release_2_5_0_alpha)
- [OrcaSlicer Design tab](https://www.orcaslicer.com/wiki/design/design_tab.html) and [import and export](https://www.orcaslicer.com/wiki/general_settings/import_export)
- [Klipper command templates](https://www.klipper3d.org/Command_Templates.html), for macro parameters
- [Marlin M810–M819 G-code macros](https://marlinfw.org/docs/gcode/M810-M819.html)
- [Duet3D forum thread on M98 macro parameters](https://forum.duet3d.com/post/310462). The official [RepRapFirmware meta commands page](https://docs.duet3d.com/User_manual/Reference/Gcode_meta_commands) did not load when this was written, so check the parameter letter rules there.
- [DIN 562 M3 square nut dimensions, Aspen Fasteners](https://www.aspenfasteners.com/m3-0-5-din-562-metric-thin-square-nuts-a2-stainless-steel)
