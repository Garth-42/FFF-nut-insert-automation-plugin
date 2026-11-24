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

## After the first probe runs in OrcaSlicer 2.5.0 (10 Nov 2026)

28. **`orca.request_permissions` is called at module load**, for read access to every
    entry of `sys.path`. This call is not in the spec's API table; it comes from the probe
    log (rule 3). Without it the first numpy use raises about 120 permission prompts. The
    grant covers Orca's bundled Python library and its plugin package folder, read-only.
29. **A part's type is read, and a nut body that still prints is `E_NOT_MODIFIER`.** The
    spec says the type cannot be read; the probe showed `is_modifier()` works. The error
    blocks the slice with the fix in the message, instead of surfacing only at export.
    The pocket proof at export stays.
30. **`PartSnapshot` gained `kind`**: "part", "modifier", "other" or "unknown". Parts of
    kind "modifier" or "other" are not walls any more, which removes the spec's risk "a
    non-nut modifier that overlaps a pocket would be measured as a wall". Snapshots built
    without a kind (tests, the command line) behave as before.
31. **The nut frame takes the three largest perpendicular faces directly**, and only the
    40 largest face directions are grouped. The real `NUT_M3SQ` body has 5,818 triangles
    from its threaded hole; merging every facet direction was needless work inside the
    100 ms budget.
32. **The probe prints nothing and shows its output in its own tab.** It no longer
    matches the spec's "prints lines prefixed NUTPROBE", because reading a log file was
    not possible: no `python_*.log` was found.
33. **The plugin module loads without numpy.** `nut_inserter/__init__.py` no longer
    imports `state`, `adapter` or anything else that needs numpy at module level, unlike
    the spec's skeleton. Each capability method imports `state` when it is called. Orca
    shows the permission request only after the module has loaded, and importing numpy
    before that would raise about 120 prompts. The permission code lives in the
    numpy-free `permissions.py`.
34. **Install-session mode.** In the session the plugin is installed in, it raises one
    "restart OrcaSlicer" notification and does nothing else: script, tab and slicing step
    answer with that notice. The permission granted at install was not active until the
    next start, so doing real work there raised about 120 prompts. The session is
    recognised by an empty stored config; each capability then stores `{"activated": true}`.
    For the slicing capability that marker is replaced by the real settings on the first
    save, which also counts as non-empty.
35. **Activity list.** `state.note()` keeps the last 80 events (checks, each slicing step's
    first call, the export result, any exception with file and line) and the panel shows
    them. New page messages `get_log` / `log`. Where Orca writes `print()` output is not
    known, so without this a silent failure in a slicing step could not be seen at all.
36. **"All clear" notification, and a time on every notification.** Orca gives a plugin no
    way to close a notification, so an error stayed on screen after it was fixed. When a
    check finds nothing wrong after one that did, the plugin raises a regular notification
    saying earlier nut messages no longer apply.
37. **`state` is imported with `importlib.import_module`, not `from . import state`.** When
    the package's module object is replaced (a second copy of the plugin, or Orca loading
    it again), the from-import fails although `nut_inserter.state` is still loaded. The
    one `state` module, and with it the cached report, is shared by every load.
38. **`on_unload` closes the panel and forgets the tab, and `broadcast` skips pages that
    no longer answer.** A second load would otherwise leave two panels and stale tabs.

## RepRapFirmware first (24 Nov 2026)

39. **Insert blocks go after the layer's retract, wipe and object label.** The spec puts a
    block on the line after the layer's last extruding move. OrcaSlicer writes the layer's
    object label comment, `;LAYER_CHANGE`, the retract, the wipe and, for Klipper,
    `EXCLUDE_OBJECT_END` after that line, so the block ran inside the object's label with
    the print tool not retracted. Klipper's exclude_object and RepRapFirmware's M486 skip
    the moves of a cancelled object while it is current. Cancelling that object mid-print
    would have dropped the macro's moves while its other commands still ran.
    `gcode/place.py` now moves the block past the retract (an E move or a bare `G10`), the
    wipe and any label that ends an object (`EXCLUDE_OBJECT_END`, `M486 S-1`,
    `; stop printing object`). It stops before anything that starts the next layer (a Z
    move, extrusion, a prime or `G11`, an object label, a tool change, a positioning or
    extruder mode change), and after the last extrusion before anything but harmless lines,
    so it never enters the end G-code. The macro contract changes with it: the print tool
    is normally retracted when the block starts, and the macro undoes only the retraction it
    adds itself. Agreed with Garth on 24 Nov 2026. The rules are tested on the real Klipper
    export and on variants with comment labels only and with M486 labels; a real
    RepRapFirmware export should confirm them.
40. **An export with errors raises a notification once it has finished.** With `on_error`
    set to `skip`, a nut left out at export was named only in a G-code comment; with
    `block`, only Orca's failure dialog said so. Garth asked for a pop-up warning in both
    cases (24 Nov 2026). The export step runs on the slicing thread, where a notification
    could deadlock, so it only keeps the text. The plugin raises it on Orca's
    `GCodeExportFinished` event, which the spec does not list but the probe found in
    `orca.LifecycleEvent`, and only on the main thread. When that event does not come, the
    next check or panel message raises it. Items left out raise a warning; a refused
    export raises an error.

## Heat-set inserts, milestone 1 (24 Nov 2026)

41. **Settings schema 2.** The settings document gains a `heatset` section, one profile per
    heat-set tool (`heatsetcore.profile`). `library.migrate()` turns a schema-1 document
    into schema 2 by adding the default section and changing nothing else.
    `state.read_config`, the panel's save and the command line run it before validating.
    Without it, `read_config` would treat a schema-1 library as unusable and show the
    defaults, and the next save would overwrite the tuned nut ranges. Bodies named
    `HEATSET_<key>` are neither walls nor nut records in the nut detection.
42. **The heat-set profile differs from docs/HEATSET_GCODE_SPEC.md** as Garth decided on
    24 Nov 2026:
    - Bodies are named `HEATSET_<key>`, not `HSI_<key>`. The key is the profile's
      `insert_key`, which may contain dots (`M3x5.7`), unlike a nut key.
    - `firmware` defaults to `reprapfirmware` (spelled as the nut settings spell it, not
      `rrf`) and `timing` to `after_layer`: the printer tests run on RepRapFirmware 3.6, and
      inserts go in right after the layer that finishes the hole's rim.
    - `insert_temp` is a manual override; empty means automatic. Automatic is the print
      tool's temperature in the G-code plus the new `insert_temp_offset` (15 °C, the spec's
      "+10–20 °C"). The spec's per-filament table is kept as `filament_temps`, the fallback
      when the G-code sets no temperature.
    - New TBD variables: `magazine_capacity` (rule 9 needs a number), and
      `min_contact_area` and `max_height_ratio` for the hold-down warning.
    - TBD is a `tbd` list of variable names; each holds the spec's placeholder until
      measured. Profiles are found by `insert_key`, which must be unique.

## Heat-set inserts, milestones 2 and 3 (24 Nov 2026)

43. **The RepRapFirmware template set.** The spec gives exact templates for Klipper only and
    says RRF follows "as macro files with the same command names". `heatsetcore/emit.py`
    writes each command as `M98 P"heatset/<name>.g"` with single-letter parameters, as
    approved by Garth on 24 Nov 2026 (docs/heatset-plan.md, "Emitted lines"). The hot push
    is one call (`push.g`) instead of `_HS_PUSH_START`, the ticks and `_HS_PUSH_END`, since
    an RRF macro can loop on the float with `G38.3`; `push_step` and `ticks` stay in the
    profile and the header for Klipper. Speeds are mm/s with one decimal under `V`;
    temperatures are whole degrees, with one decimal only when there is a fraction. The
    golden file is `tests/data/heatset_golden_rrf.gcode`.
44. **`profile.derived` moved to `routine.derived`.** The profile module holds data and
    validation; the routine math is in `routine.py`, with the heights table and each insert's
    positions, so the emitter writes no number of its own.

## Heat-set inserts, milestone 4 (24 Nov 2026)

45. **How `heatsetcore/place.py` reads the spec's placement rules.**
    - The header goes before the first object label, which comes after the start G-code,
      or before the first Z move when the file has no labels. The spec says "right after
      the slicer's start G-code", which a file does not mark without comments.
    - Blocks use `nutcore.gcode.place.block_after` (#39), which now also steps past a nut
      block written at the same point, so the nut block comes first, as agreed.
    - `z_top` snaps to the top of the first layer printed around the hole at or above the
      modelled top. The empty-hole proof checks the layers between the hole's bottom and
      that layer, with a circle of the hole radius less `PROOF_INSET`, the same margin as
      the nut proof.
    - The preheat goes after the last `M73` whose R is at least `preheat_lead`, rounded up
      to whole minutes, above the R at the block. Without `M73` it goes `preheat_layers`
      layers below the block. It never goes before the previous block.
    - Keep-out (rule 8) is checked against the extrusion printed before the block. With
      `after_layer` nothing above `z_top` is printed yet, so it only stops `end_of_print`.
    - `OBJECT` is the label in force where the hole's rim layer is printed: Klipper's
      `EXCLUDE_OBJECT_START` name, the text of the comment label RRF reads, or the name an
      `M486 A` gave the index.
    - Rule 5 (TBDs), a missing insert temperature and rule 6 apply to every insert. Rule 9
      leaves out the inserts done last. All of them follow `on_error` like any other error;
      a skipped insert is named in a `; HEATSET skipped` comment. An insert with nothing
      printed around it is skipped quietly (`N_NOT_ON_PLATE`), as nuts are.
    - The print temperature is read at the first block from `M104`, `M109`, `G10 P S` and
      `M568 P S`, for the active tool. The header stays ASCII: the degree sign is dropped.
