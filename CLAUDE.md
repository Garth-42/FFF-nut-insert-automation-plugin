# Nut inserter: rules for every session

The full design and build brief is `docs/SPEC.md`. Read it before changing behaviour.
Deviations from it are logged in `docs/DECISIONS.md`.

## Rules

1. Only the `nut_inserter` package may import `orca`. `nutcore` is plain Python 3.12 + numpy
   and its tests must pass without Orca.
2. Do not invent `orca` calls. The only allowed calls are in the API table in `docs/SPEC.md`.
   If you need another, record it in `docs/api-gaps.md` and build the fallback.
3. When `docs/probe-log.txt` disagrees with the spec, the log wins. Record the difference in
   `docs/api-facts.md` and change only the `nut_inserter` package.
4. Never crash the host. Every method Orca calls goes through `state.guarded`, which prints
   the traceback and returns a failure result.
5. Start no threads, open no network connections, spawn no processes, and touch no file except
   the G-code file handed to the export step.
6. Keep lifecycle-event handlers and page-message handlers under 100 ms. If a check would take
   longer, mark the report stale instead.
7. Lengths are millimetres, angles are degrees, coordinates are bed coordinates unless a name
   says otherwise. Z is up.
8. Commit after each milestone with its checks passing. Log every deviation from the spec, and
   the reason, in `docs/DECISIONS.md`.

## Commands

- `uv run pytest -q` runs the tests.
- `uv run ruff check` lints.
- `uv build` makes `dist/nut_inserter-<version>-py3-none-any.whl`.
- `uv run python -m nutcore.cli check part.stl NUT_M3SQ=nut.stl`
- `uv run python -m nutcore.cli inject report.json in.gcode --firmware klipper`

## Layout

- `src/nutcore/` detection, checker, report, G-code export. No Orca imports.
- `src/nut_inserter/` the Orca plugin. `adapter.py` is the only module that calls `orca.host`.
- `tests/builders.py` synthetic meshes and G-code. `tests/fake_orca/orca/` stand-in `orca` module.
- `probe/nut_api_probe.py` single-file plugin a person runs in Orca to settle open API questions.
