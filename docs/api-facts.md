# API facts from the probe

**No probe log yet.** This file is filled from `docs/probe-log.txt` after a person runs
`probe/nut_api_probe.py` in OrcaSlicer 2.5 (see `docs/manual-test.md`). Until then the
plugin follows the API table in `docs/SPEC.md`, read from Orca's documentation on
10 Nov 2026.

When the log disagrees with the spec, the log wins: record the difference here and
change only the `nut_inserter` package.

## Open tests the probe answers

| Question | Answer from the log |
| --- | --- |
| May a slicing step read the model from its worker thread? | pending |
| How do bed coordinates map to G-code coordinates on plates after the first? | pending |
| Setting key for G-code flavor (`gcode_flavor`?) and its values | pending |
| Setting key for print order (`print_sequence`?) and its values | pending |
| Is a part's type readable or settable? | pending |
| Do pages receive objects or JSON strings? (`adapter.POST_AS_JSON_STRING`) | pending |
| Does `get_config()` return a JSON string for a nested default config? | pending |
| Is `volume.name` an attribute or a method? | pending |
| Does WebGL work in plugin pages? | pending (not needed) |
| Layer-change comment format in exported G-code | pending (not used) |

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
- **A script capability's `execute` ran on a background thread** (the blocked opens were
  not on the main thread), against the spec's "UI thread" note. Unconfirmed until the
  probe's own thread line is read.

Consequences for the plugin, not yet applied: `state.guarded` prints tracebacks and the
export step prints a status line and opens the G-code file. If `print` is the cause, both
must stop printing.
