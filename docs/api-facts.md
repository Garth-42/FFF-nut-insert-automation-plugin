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
- **One flood remained, in the session where the request was first granted.** There,
  `volume.matrix()` with numpy not yet imported flooded again. In later sessions the same
  step, and steps 1 to 8 in sequence, raised no prompts (reported by Garth). So the
  likely explanation is that a grant takes effect from the next start of Orca. That is
  an inference from three sessions, not something Orca documents. The manual test says to
  restart Orca once after granting. The plugin also imports numpy itself, from a
  capability method, before any host call that returns an array.
- **Nothing that imports numpy may run while Orca loads the plugin module.** The request
  is shown only after `register_capabilities()` returns. A test enforces this.

## Confirmed in Orca

| Fact | Detail |
| --- | --- |
| Page messages | The page receives objects and JSON strings alike. `on_message` gets a `dict`. `adapter.POST_AS_JSON_STRING = False` is right |
| Threads | `get_ui`, `on_message` and lifecycle events run on `MainThread`. `on_load` and a script's `execute` run on a background thread (`Dummy-N`) |
| UI-thread calls | `orca.host.app_info()` raises "must be called from the UI thread" from a script. `push_notification` from a script's thread returned without error (run 6). Panel `post` and `create_dock_panel` from a background thread are untested |
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
| Script `execute` runs on the UI thread | Background thread | Open: the check posts to pages and raises notifications from there |
| "Create the dock panel in `on_load()`" | `on_load` runs on a background thread | Open: unverified whether `create_dock_panel` works there |
| `get_default_config()` supplies the defaults | Only for "Restore defaults" | None needed |
| Logs: `print()` goes to `log/python_*.log` | `print()` raises no prompt, but no such file was found, so where the text goes is unknown | Errors are also shown in the panel and tab |
| At post-process `ctx.print` is `None`; the model must not be read from a slicing step | `ctx.print.model()` is meant for exactly that | Not used yet |
| Plate information is not available | `current_plate_index()` exists; per-object plate does not | Not used yet |

## Still open

| Question | How it gets answered |
| --- | --- |
| Do `create_dock_panel` in `on_load` and panel `post` work from a background thread? | Manual check A with the wheel |
| What do `ctx.print`, the layers and `ctx.config_value` give at slice time? | Probe: slice with it installed |
| Does opening `ctx.gcode_path` raise a prompt? | Probe: export with it installed, or manual check D |
| Does a grant need a restart to take effect? | Likely yes (see above). Manual check A: note whether the first session prompts |
| How do bed coordinates map to G-code coordinates on plates after the first? | Not probed yet |
