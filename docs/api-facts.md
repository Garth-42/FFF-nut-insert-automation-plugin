# API facts from the probe

Source: `docs/probe-log.txt`, runs 1 to 5, OrcaSlicer 2.5.0 build 40ecc66f on macOS,
bundled Python 3.12.13. When the log disagrees with `docs/SPEC.md`, the log wins: record
the difference here and change only the `nut_inserter` package.

## The permission prompts

- **Cause, confirmed in run 5.** OrcaSlicer asks for permission each time a plugin opens
  a file, including the files Python reads to import a module. numpy is not loaded when a
  plugin starts. The first call that returns a numpy array (`volume.matrix()` in the run)
  imported 122 modules: one prompt each, with no "remember" option and no file name.
- **Fix, seen working in run 6.** `orca.request_permissions(fs_read=[...])`, called
  while Orca loads the module, with a target ending in `/*` for each folder tree. Orca
  showed one request on activation. In the next session `import numpy` from a script
  action loaded its 122 modules with no prompt, and mesh arrays, `print()` and
  `push_notification` raised none either.
- **What the plugin asks for.** Read access to every entry of `sys.path`: Orca's bundled
  Python library and its plugin package folder (`<data>/python/packages/cp312`, where
  numpy 2.5.4 is installed). See `nut_inserter/permissions.py`.
- **The install session still floods.** Seen three times: probe 0.7.0 (step 4), and the
  plugin wheel 0.2.0, whose `on_load` imported numpy right after activation. In every
  later session the same code raised no prompts. So a grant appears to take effect from
  the next start of Orca. That is an inference from these sessions, not something Orca
  documents.
- **What the plugin does about it (0.2.1).** In the session it is installed in, it only
  raises a notification asking for a restart and imports nothing. It recognises that
  session by its empty stored config (`permissions.first_session`).
- **Nothing that imports numpy may run while Orca loads the plugin module.** The request
  is shown only after `register_capabilities()` returns. A test enforces this.

## Confirmed in Orca

| Fact | Detail |
| --- | --- |
| Page messages | The page receives objects and JSON strings alike. `on_message` gets a `dict`. `adapter.POST_AS_JSON_STRING = False` is right |
| Threads | `get_ui`, `on_message` and lifecycle events run on `MainThread`. `on_load` and a script's `execute` run on a background thread (`Dummy-N`) |
| UI-thread calls | `orca.host.app_info()` raises "must be called from the UI thread" from a script. `push_notification`, `create_dock_panel` and panel `post` all worked from `on_load`'s background thread: the plugin's panel, report and error notification appeared (screenshot, 10 Nov 2026) |
| Lifecycle context | `code`, `name`, `previous_name`, `index`, `id`, `dirty`, `source`, `msg`. `ObjectAdded` carried `name = 'Configuration 1.step'`, `index = -1` |
| Settings | `get_config()` returns a JSON string, `"{}"` if never saved. `get_default_config()` is only what "Restore defaults" writes. The plugin applies its own defaults when the stored config is empty, which is the documented pattern |
| Body names | The STEP body name survives import: volume 0 is `'NUT_M3SQ'`, volume 1 is `'SOLID'`. The object is named after the file |
| Part type | `volume.is_modifier()`, `is_model_part()`, `type()` work. Both volumes were `ModelPart` |
| Names | `volume.name`, `object.name`, `object.printable` are properties |
| Mesh without numpy | `mesh.vertex(i)` gives `(x, y, z)`, `mesh.triangle(i)` gives `(a, b, c)`, plus `vertex_count()`, `triangle_count()`, `volume()`. No prompts |
| Mesh and matrices with numpy | `vertices()` (N, 3) float32 and `triangles()` (M, 3) int32 are zero-copy and read-only; `matrix()` is a 4 x 4 float64 copy. All "require numpy" |
| Transforms without numpy | `offset()`, `rotation()`, `scaling_factor()`, `mirror()` on volumes and instances return tuples |
| Plate | `model.current_plate_index()` returned 0. The single object sat at instance offset (150, 150, 6.111) |
| A real nut body | Garth's `NUT_M3SQ` has 2,909 vertices and 5,818 triangles (threaded hole) and measures 5.5 x 5.5 x 1.8 mm exactly. Its host has 24 triangles |

## Read from docstrings, not yet seen working

| Call | What the docstring says | Use |
| --- | --- | --- |
| `ctx.print` | "The orca.host.Print being sliced". `ctx.print.model()` is "the Print's own Model snapshot (worker-thread stable). Inside slicing hooks use THIS, never orca.host.model()" | The slice gate could measure the model actually being sliced, instead of trusting a cached report |
| `ctx.object` | A `PrintObject` for object-scoped steps, else `None` | |
| `PrintObject.layers()`, `Layer.print_z`, `slice_z`, `height`, `lslices()` | Layers bottom-up; `lslices` are the merged islands of a layer | Layer heights and pocket outlines without parsing G-code; maybe cutting the pocket out of the layers |
| `ctx.gcode_path`, `ctx.output_name`, `ctx.host` | Set only at `psGCodePostProcess` | |
| `ctx.config_value(key)` | "Serialized value of a resolved print config option, or None" | Key names still unverified |
| `push_notification(level, text, hyper_text='', on_click=None)` | A clickable label | "Open the Nuts tab" |
| `has_config_ui()`, `get_config_ui()` | A capability's own settings page inside the Plugins dialog, with `window.orca.getConfig()/saveConfig()` | An alternative home for the library editor |
| `orca.host.plugin.storage` | Unknown | |

## Differences from the spec

| Spec says | Orca does | Plugin change |
| --- | --- | --- |
| Part type is not readable | `is_modifier()`, `is_model_part()` work | Done: `adapter.part_type()`, finding `E_NOT_MODIFIER`, modifiers are no longer walls |
| Threads, files and network raise prompts | So does every module import | Done: `request_permissions` at load, numpy imported only after it. Seen working in the probe |
| Script `execute` runs on the UI thread | Background thread. Posting to the panel and raising a notification from a background thread worked in `on_load`; from `execute` it is untested | None so far |
| "Create the dock panel in `on_load()`" | `on_load` runs on a background thread, and creating the panel there works | None needed |
| `get_default_config()` supplies the defaults | Only for "Restore defaults" | None needed |
| Logs: `print()` goes to `log/python_*.log` | `print()` raises no prompt, but no such file was found, so where the text goes is unknown | Errors are also shown in the panel and tab |
| At post-process `ctx.print` is `None`; the model must not be read from a slicing step | `ctx.print.model()` is meant for exactly that | Not used yet |
| Plate information is not available | `current_plate_index()` exists; per-object plate does not | Not used yet |

## The first export (10 Nov 2026, wheel 0.2.0)

`tests/data/sample.gcode` is the file Garth exported with the plugin installed, the nut
set to Modifier and the report OK.

- **It contains no insert block and no summary.** No slicing error and no prompt were
  reported. So either the slicing capability was never called, or it failed silently.
- **Its config block has a print setting `; plugins = ` that is empty**, next to
  `; post_process = `. The likely reading: slicing-pipeline plugins are switched on per
  process preset, like post-processing scripts, and "Nut insert" was not switched on.
  Unconfirmed. Wheel 0.2.2 adds an Activity list to the panel that records every slicing
  step that reaches the plugin, which settles it either way.
- **Setting keys confirmed from the same block:** `gcode_flavor = klipper` and
  `print_sequence = by layer`.
- **Bed coordinates equal G-code coordinates on plate 1**: run offline, the export logic
  finds the pocket at the reported X 164.706 Y 158.320, proves it empty, and writes the
  block after the layer at Z 3.0 (`tests/test_gcode.py::test_real_sample_from_orca`).
- The file has no `T<n>` line (single extruder), so `{tool}` renders as -1.
- A notification cannot be closed by the plugin: `push_notification` returns nothing.

## The second export attempt (10 Nov 2026)

- **Slicing plugins are switched on per process preset.** Once Garth enabled "Nut
  insert" in the slicer's settings, OrcaSlicer called the plugin at export. This is the
  `plugins` print setting seen empty in the first exported file. Where exactly the
  switch sits in the UI has not been written down yet.
- **A failure from the export step is shown as a dialog**: "Orca Slicer error.
  Post-processing plugin Nut insert failed. Error: <the message the plugin returned>".
- **A wheel is unpacked next to itself**:
  `<data>/orca_plugins/<wheel file name>/__whl_extracted__/nut_inserter/nut_inserter/__init__.py`.
- **Two versions were installed at once** (0.2.0 and 0.2.2). The panel came from 0.2.2:
  its Activity list showed checks of 6 to 14 ms and no slicing step. The export step ran
  from 0.2.0 and failed with "cannot import name 'state' from 'nut_inserter'". Both
  copies are the same Python package name, so the second one loaded replaced the first's
  module object while `nut_inserter.state` stayed in `sys.modules`. Wheel 0.2.3 imports
  `state` in a way that survives this, but the real fix is to keep one copy installed.

## The first working export (10 Nov 2026, wheel 0.2.3)

With one copy of the plugin installed and "Nut insert" added under the process setting
**Slicing pipeline plugin** (enable it, then "+ Add Plugin"), the exported file contained:

```
; HEADER_BLOCK_END
; NUT_INSERT_SUMMARY firmware=klipper inserted=1 skipped=0
; nut 1 NUT_M3SQ FLAT X164.706 Y158.320 Z1.900 after layer_z=3.000
...
G1 X111.068 Y125.165 E.05401
;NUT_INSERT_BEGIN layer_z=3.000 count=1
INSERT_NUT KEY=M3SQ CLASS=FLAT X=164.706 Y=158.320 Z=1.900 Z_LOW=1.000 YAW=0.00 FEEDER=1 TOOL=-1
;NUT_INSERT_END
; stop printing object Configuration 1.step id:0 copy 0
;LAYER_CHANGE
;Z:3.2
```

- This is line for line what the export logic produced offline on the first file. Apart
  from these lines the two exports differ only in the settings named below.
- **No permission prompt at export.** Reading and writing `ctx.gcode_path` needs no grant.
- **`ctx.config_value("gcode_flavor")` works**: firmware `auto` resolved to Klipper.
- **How Orca stores the switch**: `slicing_pipeline_plugin = "Nut insert"` and
  `plugins = "nut_inserter-0.2.3-py3-none-any;;Nut insert"`. The second names the wheel
  file, version included. So after installing a newer wheel the plugin most likely has to
  be added to the process preset again. Not yet observed.

The panel's Activity list from that run:

- **Checks took 5 to 13 ms** on the real part, well inside the 100 ms event budget. Model
  events arrive in bursts (several checks in one second while the part is edited).
- **Steps that reached the plugin, in order:** `posSlice`, `posPerimeters`,
  `posPrepareInfill`, `posInfill`, `posIroning`, `posSupportMaterial`,
  `posDetectOverhangsForLift`, `psWipeTower`, `psSkirtBrim`, `posSimplifyPath`, and six
  seconds later `psGCodePostProcess`. The slice gate at `posSlice` passed.
- **`ctx.gcode_path` is a working copy in the system temp folder**:
  `<tmp>/orcaslicer_501/orcaslicer_model/<day>/<session>/Metadata/.22851.0.gcode.pp`.
  The plugin edits that, and Orca then writes the user's file from it.

## Still open

| Question | How it gets answered |
| --- | --- |
| What do `ctx.print`, the layers and `ctx.config_value` give at slice time? | Probe: slice with it installed |
| Does a grant need a restart to take effect? | Apparently yes (see above) |
| How do bed coordinates map to G-code coordinates on plates after the first? | Not probed yet |
