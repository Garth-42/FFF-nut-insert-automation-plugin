# API facts from the probe

Source: `docs/probe-log.txt`, OrcaSlicer 2.5.0 build 40ecc66f on macOS. Only step 1 of the
probe (the API surface) has run so far; the model, slicing and export steps are pending.

When the log disagrees with the spec, the log wins: record the difference here and
change only the `nut_inserter` package.

## Answered by run 1

| Question | Answer |
| --- | --- |
| Do pages receive objects or JSON strings? | Both arrive in the page. `on_message` gets a `dict` in Python. `POST_AS_JSON_STRING = False` is right |
| Which thread runs what? | `get_ui`, `on_message` and lifecycle events: `MainThread`. `on_load` and a script's `execute`: a background thread (`Dummy-N`, a new one per script run) |
| What does a lifecycle event carry? | A context with `code`, `name`, `previous_name`, `index`, `id`, `dirty`, `source`, `msg`. `ObjectAdded` gave `name = 'Configuration 1.step'` (the imported file) and `index = -1` |
| Does `get_config()` return the default config? | No. It returned the string `'{}'` although `get_default_config()` returned a nested dict. The plugin already falls back to its own defaults in that case |
| Does WebGL work in plugin pages? | Yes (WebKit). Not needed |
| Do the names in the spec's API table exist? | Yes: `Step.posSlice`, `Step.psGCodePostProcess`, all eight lifecycle events, both notification levels, `create_dock_panel`, `push_notification` |

## Found but not in the spec's API table

Signatures are from the docstrings in probe run 2. "Seen working" means a probe step has
called it in Orca; until then it is not used in the plugin (rule 2).

| Call | Signature | Why it matters | Seen working |
| --- | --- | --- | --- |
| `orca.request_permissions` | `(fs_read=[], fs_readwrite=[], network_http=[], network_socket=[], process=[], threading=False, network=[])`, called "while OrcaSlicer loads your module" | Ask once for file access instead of one prompt per open. The docstring was cut off, so what a path may be is not known yet | no |
| `ModelVolume.type()` | `-> ModelVolumeType` (`ModelPart`, `ParameterModifier`, `NegativeVolume`, ...) | A part's type is readable | no |
| `ModelVolume.is_modifier()`, `is_model_part()` | `-> bool` | The Modifier step can be checked directly instead of from the G-code | no |
| `Model.current_plate_index()` | `-> int` | The selected plate. Which plate an object is on is still not exposed | no |
| `TriangleMesh.vertex(i)`, `triangle(i)`, `vertex_count()`, `triangle_count()`, `volume()` | `vertex(i) -> (x, y, z)` tuple of floats, `triangle(i) -> (a, b, c)` tuple of ints | Reads a mesh without numpy arrays and without prompts | **yes** (run 3) |
| `ModelVolume` / `ModelInstance` `.offset`, `.rotation`, `.scaling_factor`, `.mirror` | unknown | Transforms that may not need numpy arrays | no |
| `Print.objects`, `PrintObject.layers`, `Layer.print_z`, `slice_z`, `lslices` | unknown | Sliced layers may be readable in a slicing step: layer heights and pocket outlines without parsing G-code | no |
| `orca.host.plater()` | `-> Plater` with `project_path()`, `is_project_dirty()`, `export_3mf_copy(path)` | Project path | no |
| `push_notification` | `(notification_level, text, hyper_text='', on_click=None)` | A clickable "open the Nuts tab" link in notifications | no |
| `orca.host.ui.message` | `(text, title, buttons, icon) -> str` | A modal message box | no |
| Events `SliceStarted`, `GCodeExportStarted`, `PlateSelected`, `SlicingJobComplete` | on `LifecycleEvent` | Refresh the report right before slicing | no |
| `get_config_ui`, `has_config_ui`, `get_config_version` | on every capability base | Orca may host a settings page for a capability | no |

Also confirmed: `volume.name` and `object.name` are properties, not methods. Each run of
a script action gets a new background thread (`Dummy-2`, `Dummy-3`).

## Still open

| Question | Answer |
| --- | --- |
| Which call raises the permission flood? | Something in the transform calls of probe 0.6.0 step 4 (`bounding_box`, `scaling_factor`, `mirror`, `offset`, `rotation`, `matrix`). Names, types and point-by-point mesh reads raise none. Which call exactly, and whether it is the numpy import, is pending: step 4 output |
| Can `request_permissions` stop the flood, and with which paths? | pending: full docstring in probe 0.6.0 step 1 |
| May a slicing step read the model from its worker thread? | pending |
| How do bed coordinates map to G-code coordinates on plates after the first? | pending |
| Setting keys for G-code flavor and print order, and their values | pending |

## Differences from the spec

From the first probe run on OrcaSlicer 2.5.0 build 40ecc66f (macOS), 10 Nov 2026. Source:
Orca's `debug_*.log`, not a probe log.

- **Running the probe's script action raised 99 `[AUDIT BLOCKED] plugin=nut_api_probe
  event=open` prompts in 1.4 s.** The cause is not confirmed. The count is close to the
  number of lines the script printed, and no `python_*.log` was created, so the leading
  guess is that each `print()` opens the Python log file and is audited as the plugin.
  The other candidate is the numpy import behind `mesh.vertices()`. Probe 0.3.0 separates
  the two.
- **No `python_*.log` exists in the data folder's `log` directory**, against the spec's
  "Logs: `print()`" row.
- **A script capability's `execute` and every `on_load` run on a background thread**
  (`Dummy-1`), against the spec's "UI thread" note. Confirmed by probe run 1. The plugin
  creates its dock panel in `on_load` and posts to pages and raises notifications from
  `execute`; whether those `orca.host.ui` calls are safe off the main thread is not known.

Consequences for the plugin, not yet applied: `state.guarded` prints tracebacks and the
export step prints a status line and opens the G-code file. If `print` is the cause, both
must stop printing.
