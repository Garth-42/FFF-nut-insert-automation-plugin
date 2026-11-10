# API facts from the probe

Source: `docs/probe-log.txt`, runs 1 to 5, OrcaSlicer 2.5.0 build 40ecc66f on macOS,
bundled Python 3.12.13. When the log disagrees with `docs/SPEC.md`, the log wins: record
the difference here and change only the `nut_inserter` package.

## The permission prompts

- **Cause, confirmed in run 5.** OrcaSlicer asks for permission each time a plugin opens
  a file, including the files Python reads to import a module. numpy is not loaded when a
  plugin starts. The first call that returns a numpy array (`volume.matrix()` in the run)
  imported 122 modules: one prompt each, with no "remember" option and no file name.
- **Fix, not yet seen working.** `orca.request_permissions(fs_read=[...])`, called while
  Orca loads the module. A target ending in `/*` grants a folder tree. Orca shows one
  request after `register_capabilities()` returns; denying it aborts the plugin load.
  Targets already granted are not asked for again.
- **What the plugin asks for.** Read access to every entry of `sys.path`: Orca's bundled
  Python library and its plugin package folder (`<data>/python/packages/cp312`, where
  numpy is installed). See `adapter.permission_targets()`.
- **Open risk.** The prompt said the open "does not expose a target the audit hook can
  display". If the audit event carries no path, a path grant cannot match it and the
  flood would stay. Probe 0.7.0 step 5 tests exactly this.

## Confirmed in Orca

| Fact | Detail |
| --- | --- |
| Page messages | The page receives objects and JSON strings alike. `on_message` gets a `dict`. `adapter.POST_AS_JSON_STRING = False` is right |
| Threads | `get_ui`, `on_message` and lifecycle events run on `MainThread`. `on_load` and a script's `execute` run on a background thread (`Dummy-N`) |
| UI-thread calls | `orca.host.app_info()` raised "must be called from the UI thread" from a script. Whether `push_notification` and panel `post` do the same is open: probe 0.7.0 step 8 |
| Lifecycle context | `code`, `name`, `previous_name`, `index`, `id`, `dirty`, `source`, `msg`. `ObjectAdded` carried `name = 'Configuration 1.step'`, `index = -1` |
| Settings | `get_config()` returns a JSON string, `"{}"` if never saved. `get_default_config()` is only what "Restore defaults" writes. The plugin applies its own defaults when the stored config is empty, which is the documented pattern |
| Body names | The STEP body name survives import: volume 0 is `'NUT_M3SQ'`, volume 1 is `'SOLID'`. The object is named after the file |
| Part type | `volume.is_modifier()`, `is_model_part()`, `type()` work. Both volumes were `ModelPart` |
| Names | `volume.name`, `object.name`, `object.printable` are properties |
| Mesh without numpy | `mesh.vertex(i)` gives `(x, y, z)`, `mesh.triangle(i)` gives `(a, b, c)`, plus `vertex_count()`, `triangle_count()`, `volume()`. No prompts |
| Mesh and matrices with numpy | `vertices()` (N, 3) float32 and `triangles()` (M, 3) int32 are zero-copy and read-only; `matrix()` is a 4 x 4 float64 copy. All "require numpy" |
| Transforms without numpy | `offset()`, `rotation()`, `scaling_factor()`, `mirror()` on volumes and instances return tuples |
| Plate | `model.current_plate_index()` returned 0. The single object sat at instance offset (150, 150, 6.111) |
| A real nut body | Garth's `NUT_M3SQ` has 2,909 vertices and 5,818 triangles (threaded hole). Its host has 24 triangles |

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
| Threads, files and network raise prompts | So does every module import | Done: `request_permissions` at load. Unverified |
| Script `execute` runs on the UI thread | Background thread | Open: the check posts to pages and raises notifications from there |
| "Create the dock panel in `on_load()`" | `on_load` runs on a background thread | Open: unverified whether `create_dock_panel` works there |
| `get_default_config()` supplies the defaults | Only for "Restore defaults" | None needed |
| Logs: `print()` goes to `log/python_*.log` | No such file was found | Open: probe 0.7.0 step 7 |
| At post-process `ctx.print` is `None`; the model must not be read from a slicing step | `ctx.print.model()` is meant for exactly that | Not used yet |
| Plate information is not available | `current_plate_index()` exists; per-object plate does not | Not used yet |

## Still open

| Question | Probe 0.7.0 step |
| --- | --- |
| Does the `request_permissions` grant stop the import flood? | 5 |
| Does `print()` raise a prompt? Where does it go? | 7 |
| Does `orca.host.ui` work from a script's background thread? | 8 |
| What do `ctx.print`, the layers and `ctx.config_value` give at slice time? | slicing |
| Does opening `ctx.gcode_path` raise a prompt? | export |
| How do bed coordinates map to G-code coordinates on plates after the first? | not probed yet |
