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

None recorded yet.
