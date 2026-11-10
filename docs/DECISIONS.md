# Decisions and deviations from docs/SPEC.md

Each entry says what differs from the spec and why. Newest last.

## Process

1. **Milestone order and commits.** Built in the order 0, 1 (+6), 5 core, 2 to 4, because
   the export step in the plugin shell needs the G-code package. The corner class shares
   its code path with the other classes, so it landed with milestone 1 rather than as a
   separate change. No milestone is "done" in the spec's sense until its manual check in
   Orca has run; none has.
2. **Python version.** The spec says 3.12. The build machine had 3.13; `requires-python`
   is `>=3.12` and the code uses nothing newer than 3.12.
3. **Where `orca` is imported.** Only `nut_inserter/__init__.py` (capability classes) and
   `adapter.py`. `state.py` asks the adapter for result objects, so the spec's
   `state.guarded` returns `adapter.failure(...)` instead of calling `orca` itself.

## Detection

4. **Host triangle filter.** The spec keeps host triangles "with a vertex within
   `RAY_REACH`". A large flat wall has only far-away vertices and would be dropped, so
   the filter keeps triangles whose bounding box comes within reach. Hits farther than
   `RAY_REACH` from the nut face are still ignored.
5. **Drop path needs half the rays to agree on the roof** (`ROOF_AGREE = 0.5`). The
   spec's 25 % rule contradicts its own test case 18: a ledge over a third of the pocket
   is seen by 40 % of the rays and would simply become the roof. With 50 %, a partial
   cover is `E_DROP_PATH`, and a roof with a bolt hole (36 % of rays in the hole) passes.
6. **Ray origins.** Sideways rays are cast after the nut has been settled on its seat.
   Drop-path rays start on the nut's horizontal mid-plane, which is inside the nut for
   every class, so a ray cannot start behind a slanted wall of a V slot.
7. **Rim of an open-top pocket.** The walk starts at the nut's centre (walls can end
   below the nut's top) and the last step is refined by bisection, so the rim height is
   exact rather than within `RIM_STEP`.
8. **Measured half-sizes.** Gaps and the vertical half-extent `r` use the nut body's
   measured size, which is within `BODY_TOL` of the library size, so gap arithmetic is
   exact for the body as modelled.
9. **`E_NO_POCKET` alone when no face sees anything.** A nut with no host would
   otherwise also report `E_SEAT`. When the seat is missing, sideways measuring is
   skipped.
10. **`W_REACH` is measured to the top of the seated nut**, not to its seat. With the
    seat, every on-edge nut (5.5 mm tall, reach 3 mm) would warn, including the spec's
    own "ok" case 8. Change `checker.py` and `gcode/proof.py` if your tool reaches to the
    seat instead.
11. **Range checks allow 1e-6 mm**, so a pocket measured as 5.6999999 passes a 5.70
    minimum.
12. **Parts named `NUT_…` with no library entry are not walls.** They are reported as
    `E_NAME_UNKNOWN` and left out of the host, like known nuts.

## Report and messages

13. **Extra record field `window`**: the insert window `[z_from, z_to]`, `z_to` null for
    an open top. The spec's report table lists it but the JSON example does not.
14. **`export` field contents**: `layer`, `layer_z`, `z`, `z_low`, `z_high`,
    `after_line`, or `{"skipped": "N_NOT_ON_PLATE"}`. `layer` counts layers at the
    pocket, not Orca's layer number.
15. **Extra page messages `get_csv` / `csv`.** The tab shows CSV text to copy, and the CSV
    is built in Python so there is one implementation.
16. **Import and export of the library use a text box.** A plugin page cannot open or
    save files, and the plugin must not touch files.

## Plugin

17. **The slice gate fails when no check has run at all**, with the `E_STALE` message.
    The plugin cannot tell "no nuts" from "never looked". The first page `ready` and
    every model event run the check, so this should only show when those failed.
18. **The Nuts tab re-runs the check on `stale` only while it is visible**, and when it
    becomes visible again. Otherwise a hidden tab would force a slow check on every model
    change, which the event budget exists to prevent.
19. **`get_edges` takes a fresh snapshot** and is not budget-guarded. It runs only when
    the tab asks, and the result is cached by fingerprint.
20. **Saving settings re-runs the check** (or marks the report stale when checks are
    slow), because new ranges change the findings.

## G-code

21. **Print-order test.** Heights are checked per pocket, as the spec's "local layers"
    imply. A file-wide test would raise false alarms on start G-code that purges at a higher Z.
    One more test was added: no move of the pocket's upper layers may come before the
    insertion point. That catches by-object printing when the setting key is unknown.
22. **Corner pockets: the proof footprint narrows towards the bottom of the V.** With the
    full opening the V walls themselves would count as plastic in the pocket.
23. **Open-top pockets.** Open layers end at the rim. If no layer top clears the nut by
    `min_top_clearance`, the block goes after the last layer at the pocket.
24. **A file with nothing to insert is left byte-identical**: no summary is written when
    there are no blocks and no skipped nuts to name.
25. **Template values are ready-made strings** (3 or 2 decimals). A format spec such as
    `{x:.1f}` is rejected as `E_TEMPLATE` when the settings are saved.
26. **The `inject` command writes `<name>.nuts.gcode`** instead of editing its input, so
    a test file is not lost. The Orca export step edits in place, as the spec says.
27. **Arcs in R form** are read as a straight move; only I, J arcs are split. Orca writes
    I, J arcs.
