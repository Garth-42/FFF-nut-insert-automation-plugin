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
39. **The rim walk casts five rays per side, not one.** The spec's single ray from the
    nut's centre line looks straight down the bolt hole of a nut on edge, so an open-top
    slot with a bolt hole was measured as having no walls (rim at the nut's centre, false
    `E_DEPTH`). Each side now casts a row of rays spread across the nut and sees its wall
    when a quarter of them hit, the same rule as for the walls. Bolt holes are otherwise
    handled by the existing agreement rules: walls and the seat need 25 % of a face's
    rays, the roof 50 %. On the 5 x 5 grid that holds for a round hole up to 0.8 of the
    width across flats; a wider hole through the roof reports `E_DROP_PATH`.

## RepRapFirmware first (24 Nov 2026)

40. **Insert blocks go after the layer's retract, wipe and object label.** The spec puts a
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
41. **An export with errors raises a notification once it has finished.** With `on_error`
    set to `skip`, a nut left out at export was named only in a G-code comment; with
    `block`, only Orca's failure dialog said so. Garth asked for a pop-up warning in both
    cases (24 Nov 2026). The export step runs on the slicing thread, where a notification
    could deadlock, so it only keeps the text. The plugin raises it on Orca's
    `GCodeExportFinished` event, which the spec does not list but the probe found in
    `orca.LifecycleEvent`, and only on the main thread. When that event does not come, the
    next check or panel message raises it. Items left out raise a warning; a refused
    export raises an error.

## Heat-set inserts, milestone 1 (24 Nov 2026)

42. **Settings schema 2.** The settings document gains a `heatset` section, one profile per
    heat-set tool (`heatsetcore.profile`). `library.migrate()` turns a schema-1 document
    into schema 2 by adding the default section and changing nothing else.
    `state.read_config`, the panel's save and the command line run it before validating.
    Without it, `read_config` would treat a schema-1 library as unusable and show the
    defaults, and the next save would overwrite the tuned nut ranges. Bodies named
    `HEATSET_<key>` are neither walls nor nut records in the nut detection.
43. **The heat-set profile differs from docs/HEATSET_GCODE_SPEC.md** as Garth decided on
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

44. **The RepRapFirmware template set.** The spec gives exact templates for Klipper only and
    says RRF follows "as macro files with the same command names". `heatsetcore/emit.py`
    writes each command as `M98 P"heatset/<name>.g"` with single-letter parameters, as
    approved by Garth on 24 Nov 2026 (docs/heatset-plan.md, "Emitted lines"). The hot push
    is one call (`push.g`) instead of `_HS_PUSH_START`, the ticks and `_HS_PUSH_END`, since
    an RRF macro can loop on the float with `G38.3`; `push_step` and `ticks` stay in the
    profile and the header for Klipper. Speeds are mm/s with one decimal under `V`;
    temperatures are whole degrees, with one decimal only when there is a fraction. The
    golden file is `tests/data/heatset_golden_rrf.gcode`.
45. **`profile.derived` moved to `routine.derived`.** The profile module holds data and
    validation; the routine math is in `routine.py`, with the heights table and each insert's
    positions, so the emitter writes no number of its own.

## Heat-set inserts, milestone 4 (24 Nov 2026)

46. **How `heatsetcore/place.py` reads the spec's placement rules.**
    - The header goes before the first object label, which comes after the start G-code,
      or before the first Z move when the file has no labels. The spec says "right after
      the slicer's start G-code", which a file does not mark without comments.
    - Blocks use `nutcore.gcode.place.block_after` (#40), which now also steps past a nut
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

## Heat-set inserts, milestone 5 (24 Nov 2026)

47. **How `heatsetcore` finds and checks an insert** (`insert.py`, `hole.py`, `checks.py`,
    `detect.py`; cases H1–H20 in `tests/test_heatset_detect.py`).
    - **Frame.** Normals binned by direction, as the plan says. The first of the eight
      largest bins along which the body measures the profile's length and diameter, each
      within `body_tolerance_mm`, wins.
    - **Host.** The parts of the same copy that print (type part, or unknown) and are not
      nut or insert bodies. An insert body that is still a printing part is
      `E_NOT_MODIFIER`; it is never a wall of its own hole, so the hole is still checked.
    - **Hole.** Two circle fits from 5 heights × 16 rays, the second from the first's
      centre. The rim and bottom walks use 8 rays from the hole axis: 0.5 mm steps, then
      6 rounds of 15 points between the last good and the first bad step, to 3·10⁻⁸ mm, so
      a hole of exactly the needed depth passes `CHECK_EPS`. Through: no wall 0.3 mm below
      the bottom.
    - **Wall.** 36 directions × 5 heights, from the hole's wall to the next surface out. A
      flat outside face between two rays reads at most 0.4 % of (r + wall) thick. Only
      surfaces within 3 × `insert_od` of the body are cast against, so a thicker wall has
      no value and passes.
    - **Open end.** 7 rays along the axis from a disc of 0.6 r. Nothing within 50 mm above
      the rim: `UPRIGHT`. Something below the rim: `E_DROP_PATH`. Every ray stopped within
      0.2 mm of the rim is a ceiling: `INVERTED` when the hole is open below, otherwise
      `E_DROP_PATH` (closed at both ends). Otherwise a lid with a gap: `UPRIGHT` and
      `N_COVERED`.
    - **Surface.** Rays down onto rings from r + 0.75 mm out to the pad's radius less
      0.25 mm, 12 per ring. Points within 1 mm of the rim height get a plane fit, and its
      tilt is held to `axis_tolerance_deg`, which is the plan's 0.5° by default; the
      surface and the axis then share one setting.
    - **`E_INTERFERENCE` (new, not in the plan's table).** A blind hole whose bottom is
      more than `GAP_EPS` above the body's bottom: the body reaches into the floor, so the
      insert cannot go as deep as modelled. The spec's depth rule only looks at the hole.
    - **`E_NO_POCKET` and `E_DROP_PATH`** keep the nut checker's codes for the same faults.
    - **Hold-down.** Per copy: the area of the printing parts' bottom faces on the bed, and
      their height. `W_HOLD_DOWN` when the area is under `min_contact_area` or height ÷
      √area is over `max_height_ratio`.
    - **Speed.** `nutcore.rays.cast_fan` casts from points on one line in many directions,
      setting up each triangle once per direction; `beyond` gives the next surface out.
      The walks only cast against triangles near the axis. The 720-facet knurled body in a
      256-facet hole (H18) went from 107–150 ms to about 50 ms; the other cases take
      10–20 ms.
    - **Report schema 2.** Records carry `kind`, "nut" or "heatset"; a schema-1 report
      reads as nuts. The CSV adds kind, hole_diameter and wall at the end, so the existing
      columns keep their places. `detect_inserts` numbers from `first_index`, so the
      plugin can number inserts after the nuts (milestone 6).
    - **ASCII comments.** `emit.ascii_text` turns °, ², ÷, √, × and long dashes into plain
      text for G-code comments, since finding messages use them (`; HEATSET skipped`).

## Heat-set inserts, milestone 6 (24 Nov 2026, wheel 0.3.0)

48. **How the plugin runs heat-set inserts.**
    - **One check, one report.** `state.run_check` runs the nut detection, then
      `heatsetcore.detect.detect_inserts` on the same snapshot; inserts are numbered after
      the nuts. The panel, the Nuts tab, the gate and the notifications read both kinds.
    - **Rule 5 at check time.** A profile in normal mode with values still on its `tbd`
      list gives every insert of that profile `E_PROFILE`, so the panel says what to
      measure before anyone slices. The gate shows a profile problem once, without the
      insert labels, however many inserts share it. Rehearse mode clears it.
    - **One heat-set tool per print.** The G-code gets one header for one tool, so
      `detect_inserts` refuses inserts of a second profile (`E_PROFILE`), and the export
      step refuses them again rather than trust the report. The spec does not cover two
      heat-set tools.
    - **The export step.** Nut blocks first (`nutcore.gcode.inject`, which now skips
      heat-set records), then `heatsetcore.export` on its output. If either refuses, the
      file stays as Orca wrote it. When both find their own markers (Orca running the step
      twice), the result is "skipped" and the file is untouched.
    - **Inserts the checks refused** go to `place` as `refused`, so `on_error` treats them
      like inserts the G-code fails: `block` refuses the export, `skip` names them in a
      `; HEATSET skipped` comment and the pop-up lists them. Comments drop the label from the
      message, since the comment already names the insert.
    - **Tilted and inverted inserts** are not errors: each gets a `; HEATSET by hand`
      comment, and no pop-up.
    - **Filament type** comes from `ctx.config_value("filament_type")`, the first
      extruder's entry. The key name is unverified, like the others; without it the
      filament table is skipped and an insert with no print temperature is refused.
    - **Object names** come from the G-code's own labels at export, as placement already
      reads them, so the snapshot does not carry object names. The plan's architecture
      sketch expected them in the snapshot.
    - **The panel.** Three tabs: Nuts (the nut library and the shared settings), Heat-set
      (the spec's Process and Behaviour groups without the tool's hardware), and Machine
      settings (Measured and Motion, the tool number, firmware and magazine capacity), with
      one profile picker. A TBD badge marks each placeholder; entering a value, or clicking
      the badge, takes it off the list. The rule messages and derived values come from
      Python through a `check_profile` page message, so the math stays in `routine.py`.
      The tab shown is not remembered: `localStorage` would make the page write files
      (CLAUDE.md rule 5).
    - **The insert temperature used** by the last export is kept in `state` and sent to a
      page when it says "ready". The export runs on the slicing thread, which never posts to
      a page.
    - **The Nuts tab** draws each insert's two tool footprints at its top: mouth over the
      hole for the hot push, solid; pad over the hole for the press, dashed. These are the
      circles rule 8 checks.

## Heat-set inserts, milestone 7 (24 Nov 2026)

49. **The RepRapFirmware macros, `macros/heatset/*.g`.** One file per call the emitter
    writes, plus `init.g` (globals, limits, axis A, the saved magazine), `limits.g`,
    `heat.g`, `stock.g`, `fail.g`, `stop.g`, `save.g` and `refill.g`. Install guide and
    bring-up steps: `macros/heatset/README.md`. Not yet run on a printer; the static
    checks are in `tests/test_heatset_macros.py`.
    - **Abort asks instead of pausing.** The spec's abort stays in place, sets the throat
      to standby and pauses. RRF's `abort` ends the print, and after a pause (`M226`, the
      plan's choice) and a resume the print's own `G0` lines would run on with the tool
      where it stopped, the pad perhaps on the part. So `fail.g` stays in place, throat at
      standby, and asks with a blocking `M291`: "Go on" skips the rest of the insert (or
      block), lifts straight up to the block's safe height and heats again; "Stop the print"
      turns the throat and print tool heaters off and ends the print with `abort`. The raw
      moves left in a skipped insert run at the safe height, or at the routine's own
      approach height, which clears the part by design.
    - **Probes and the push use `G38.3`** (no error when nothing trips) and read the float
      afterwards, rather than `G38.2`, whose error inside a macro might end the print
      instead of reaching the macro's own failure handling. The probe never goes more than
      surface_tol + 0.05 mm below the expected trip; the press never more than press_guard
      + 0.5 mm below the probe trip.
    - **Limits cap speeds and waits, and refuse distances:** a probe or press speed over
      the limit runs at the limit; a push or unsheath over its limit stops the insert,
      since a shorter push would leave it half in. Temperatures over the limit end the print
      at the header.
    - **The magazine** persists in `/sys/heatset/count.g`: count, key and the follower's
      pending retract. A short magazine asks for a refill and the number loaded
      (`M291 S5`), or goes on without inserts. A stopped insert is not counted out.
    - **Rehearse mode** sets the tool's temperatures to 0 before selecting it, never moves
      A, skips the float checks and the probe (s = z_top + rehearse_lift), and lowers the
      pad to s for the press. The count does not change.
    - **The last insert of the print** turns the throat off in `end.g`, counted from
      `require.g`'s total.
    - **Unsheath** moves Z and A together with F = V × 60 × √2, so each moves at V, which
      needs axis A to be linear (`M584 ... R0`).
    - **Every insert is logged** to the console and `/sys/heatset/log.csv`.
    - **No LED.** The spec's amber LED is Klipper hardware; RRF warns with a message.

## Heat-set inserts, milestone 9: Klipper (24 Nov 2026, wheel 0.4.0)

50. **How the Klipper side is built.**
    - **Emitter.** The spec's Klipper templates, word for word; the worked example is
      `tests/data/heatset_golden_klipper.gcode`, taken from the spec with its 26
      `_HS_PUSH_TICK` lines, and matched byte for byte. P14 runs P1–P5 on the Klipper export
      and finds the lines inserted at the same places as for RepRapFirmware. Object names
      have `#`, `*` and `;` replaced and are shell-quoted when they hold a space or a
      quote, since Klipper ends parameters at `#` or `;` and splits them with shlex.
    - **Firmware and flavor must agree.** An export whose printer profile's G-code flavor is
      not the heat-set profile's firmware refuses every insert (`E_PROFILE`, naming both).
      Not in the spec; it stops RRF macro calls from reaching a Klipper printer and back.
    - **Macros: `firmware/klipper/heatset_macros.cfg`**, the path the spec gives, with the
      limits and names apart in `heatset_limits.cfg` (`_HS_LIMITS`) so an update of the
      macros does not overwrite them. The RRF macros stay under `macros/heatset/`.
    - **A stopped insert lifts before it pauses.** The spec stays in place. But Klipper
      cannot ask mid-print, and `RESUME` moves back to where the pause happened before the
      print's own `G0` lines run, so `_HS_ABORT` sets the throat to standby, skips the rest
      of the insert, lifts straight up to the block's safe height, and then pauses with the
      configured pause that does not park. The RRF side asks first (#49).
    - **Short magazine and cold throat pause without skipping**, as the spec says; the probe
      checks both again before it moves, so resuming before fixing them stops that insert
      instead of pushing cold or empty. Each insert sets the throat back to the insert
      temperature, since a stopped insert leaves it at standby.
    - **The throat wait is unrolled inside the macros:** `_HS_WAIT_TEMP` renders
      `temp_settle` one-second `_HS_TEMP_TICK` calls, each of which renders when it runs, as
      the G-code does for the push.
    - **Axis A** is registered by `HEATSET_CONFIG` in normal mode, only when
      `printer.gcode_move.axis_map` lacks it: Klipper refuses to register it twice. Klipper
      times an extra axis by the XYZ part of a move, so the unsheath uses F = V × 60 (RRF:
      × √2).
    - **Saved variables:** `hs_count`, `hs_key` and `hs_pending` (the follower retract still
      to take up), as the RRF side keeps them in `count.g`.
    - **Tools** are selected with klipper-toolchanger's `T<n>`, the heat-set tool needing a
      `tool_number`; the print tool comes back with `T<n>` or `UNSELECT_TOOL`, then
      `RESTORE_GCODE_STATE`. The throat's standby temperature is `_HS_LIMITS.standby_temp`,
      0 (off) by default.
    - **A stand-in for Klipper in the tests** (`tests/klipper_sim.py`, jinja2 as a dev
      dependency only) renders the macros with Klipper's own Jinja settings and runs the
      plugin's G-code through them: a normal print, rehearse mode, every failure path. It
      found `G1 A{-dist}`: with Klipper's `{ }` delimiters, `{-` is whitespace control, so
      the retract rendered as `A0.3`, forwards. A test now bans `{-` and `-}`.

## Before printer testing: stand-ins, bring-up kit, test models (25 Nov 2026)

51. **What was added to test with, and its limits.**
    - **A stand-in for RepRapFirmware** (`tests/rrf_sim.py`) runs `macros/heatset/*.g` on
      the plugin's G-code, as `tests/klipper_sim.py` does for Klipper
      (`tests/test_rrf_macros.py`: a normal print, rehearse mode, every failure path and the
      refusals). It is written from the Duet3D documentation, not from RRF's source, so
      where the documentation leaves behaviour open it takes the stricter side: `&&` and
      `||` evaluate both operands, a macro's G90/G91 and feed rate carry on after it
      returns, `if` and `!` take only booleans, and any command or function outside the
      subset the macros use is an error. Eight hand-made faults in the macros (a wrong
      surface formula, a missing wait count, no lift after a stop, the wrong tool restored,
      an inverted temperature check, no cancelled-object check, a forward retract, rehearse
      moving the follower) each make tests fail. The macros passed it unchanged.
    - **The bring-up kit.** `heatsetcore.bringup` writes the air test: one insert's routine,
      always in rehearse mode, its surface at least 5 mm (40 by default) over an empty bed,
      from the profile in the panel's exported settings. RRF gets `check_float.g`,
      `check_follower.g` and `check_probe.g`; Klipper `heatset_checks.cfg` with
      `HEATSET_CHECK_FLOAT` and `HEATSET_CHECK_FOLLOWER`, but no probe check, since Klipper's
      `PROBE` has no travel limit. All run in the stand-ins (`tests/test_bringup.py`).
    - **Test models** (`models/*.3mf`, made by `tests/models3mf.py`): ten check coupons, one
      per finding, and a bring-up coupon. The test builders' meshes are not closed, so these
      are built anew: a block whose top face stitches the hole's ring to the rectangle's
      outline, every edge shared by exactly two faces. Each coupon is one 3MF object whose
      two components are the block and the insert body. Whether Orca keeps components as
      named parts is for check F to confirm; `tests/test_models.py` reads the files back,
      checks every mesh is closed and faces outward, and gives each coupon its finding.
    - **CI.** `.github/workflows/tests.yml` runs ruff, every test and the wheel build on each
      push and pull request, on Python 3.12 (the plugin's) and 3.13. The two tests that hold
      the 100 ms handler budget (CLAUDE.md rule 6) take their limit from `tests/timing.py`,
      which CI scales by 3 through `TIME_BUDGET_SCALE`: a shared runner is slower and busier
      than a desk, where the limits stay as written. The 3MF models are compared by their
      contents, not their zip bytes, since zlib builds compress the same data differently.

## Wheel on every push to main (25 Nov 2026)

- `.github/workflows/wheel.yml` runs ruff, the tests and `uv build --wheel` on Python 3.12
  for each push to `main` (and by hand), uploads the wheel as the `nut-inserter-wheel` run
  artifact, and replaces the `main-latest` pre-release with it. A release asset needs no
  GitHub sign-in to download, unlike a run artifact, so testers use the release. The wheel
  keeps the `pyproject.toml` version, so its file name, which the process preset stores,
  changes only when the version is bumped. The release is deleted and created again on
  each push so its tag always points at the commit the wheel came from.
