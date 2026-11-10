# API facts from the probe

Source: `docs/probe-log.txt`, OrcaSlicer 2.5.0 build 40ecc66f on macOS. Only step 1 of the
probe (the API surface) has run so far; the model, slicing and export steps are pending.

When the log disagrees with the spec, the log wins: record the difference here and
change only the `nut_inserter` package.

## Answered by run 1

| Question | Answer |
| --- | --- |
| Do pages receive objects or JSON strings? | Both arrive in the page. `on_message` gets a `dict` in Python. `POST_AS_JSON_STRING = False` is right |
| Which thread runs what? | `get_ui` and `on_message`: `MainThread`. `on_load` and a script's `execute`: `Dummy-1`, a background thread |
| Does `get_config()` return the default config? | No. It returned the string `'{}'` although `get_default_config()` returned a nested dict. The plugin already falls back to its own defaults in that case |
| Does WebGL work in plugin pages? | Yes (WebKit). Not needed |
| Do the names in the spec's API table exist? | Yes: `Step.posSlice`, `Step.psGCodePostProcess`, all eight lifecycle events, both notification levels, `create_dock_panel`, `push_notification` |

## Found but not in the spec's API table

Names only. Signatures are unknown until probe 0.4.0 records their docstrings, so none of
these is used yet (rule 2).

| Name | Why it matters |
| --- | --- |
| `orca.request_permissions` | May let the plugin ask once for file access instead of one prompt per open |
| `orca.host.ModelVolumeType`, `orca.host.ModelVolume` | A part's type may be readable, which would replace the manual Modifier check |
| `orca.host.plater`, `orca.host.Plater`, events `PlateSelected`, `PlateCreated`, `PlateDeleted` | Plate information may be available, which would lift the plate-1 limit |
| Events `SliceStarted`, `GCodeExportStarted`, `SlicingJobComplete` | A chance to refresh the report right before slicing |
| `orca.host.Print`, `PrintObject`, `Layer`, `LayerRegion` | Sliced layers may be readable from a slicing step |
| `orca.host.ui.message`, `create_window` | Other ways to show a result |

## Still open

| Question | Answer |
| --- | --- |
| What raised the 99 permission prompts? | Reading the model or its meshes, not `print()`: probe 0.4.0 prints nothing and step 2 flooded again. The prompt names no file ("does not expose a target the audit hook can display") and offers only Yes or No, with no way to remember the answer. Which call, and whether it is the numpy import, is pending: probe 0.5.0 step 3 |
| May a slicing step read the model from its worker thread? | pending |
| How do bed coordinates map to G-code coordinates on plates after the first? | pending |
| Setting keys for G-code flavor and print order, and their values | pending |
| Is `volume.name` an attribute or a method? | pending |

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
