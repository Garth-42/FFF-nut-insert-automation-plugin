# Heat-set inserts: plan

Nov 24, 2026 · revision 5: RepRapFirmware first, after your answers and
`docs/HEATSET_GCODE_SPEC.md`. Built so far: milestone 0 (wheel 0.2.4), the export pop-up
(0.2.5), milestone 1, the heat-set profile and settings schema 2 (0.2.6), milestones 2
to 5: the routine math, the RRF emitter with its golden file, placement in a real export,
detection and checks (DECISIONS.md #46), and milestone 6 (wheel 0.3.0): the plugin finds
inserts, gates the slice and writes the heat-set G-code at export, with the Heat-set and
Machine settings tabs (DECISIONS.md #47). Milestone 7, the RepRapFirmware macros the
G-code calls (`macros/heatset/`, DECISIONS.md #48), is written and checked statically but
has not run on a printer: bring it up in rehearse mode first (milestone 8).

## Summary

Two documents drive the heat-set work. `docs/HEATSET_GCODE_SPEC.md`, your spec saved from the Word
file, defines the tool profile, the insertion routine, the emitted G-code and the firmware commands.
This plan covers what that spec leaves to the plugin: finding insert bodies and measuring their
holes, the checks, settings, report, slice gate, export step and pages. It also fills in the
RepRapFirmware side, which the spec only outlines and which now comes first. And it records where
the spec disagrees with your answers, with the nut plugin as built, or with a real Orca export.

What changed since revision 1:

- **RepRapFirmware first, Klipper later.** The printer tests run on RRF. The spec's Klipper templates,
  golden file and macros move to the last milestone.
- The routine is written out step by step from a tool profile, not one `INSERT_HEATSET` call.
- The insert size belongs to the tool profile (one size per tool), not to the nut library.
- The press always ends flush with the probed surface, so the sink range is gone.
- Hole size, depth and wall limits come from the profile, and failing them refuses the export.
- Blocks are placed outside the slicer's object labels (finding 1).

## Settled

| Topic | Decision | Source |
| --- | --- | --- |
| Firmware | RepRapFirmware first. Klipper follows the same routine later | Your answer, 24 Nov. The spec said Klipper first |
| Printer | RepRapFirmware 3.6, standalone: meets the 3.6.0 the design needs | Your answer, 24 Nov |
| RRF calls | The letters and file names in the table under "Emitted lines" | Approved 24 Nov |
| Block placement | After the layer's retract, wipe and object-end label, for heat-set and nut blocks. Nut blocks moved in wheel 0.2.4 | Approved 24 Nov; DECISIONS.md #39 |
| Body name | `HEATSET_<key>`, where key is the profile's `insert_key`, for example `HEATSET_M3x5.7` | Your answer, 24 Nov. The spec said `HSI_<key>` |
| Insert height | `z_top` is the top of the modelled body, snapped to the top of the layer that prints it. To be checked later against the hole's rim | Your answer, 24 Nov |
| When | `after_layer` by default: right after the layer that prints `z_top`. `end_of_print` stays available | Your answer, 24 Nov. The spec's default was `end_of_print` |
| Temperature | A manual override in the panel (blank: automatic); else the print tool's target temperature in the G-code plus `insert_temp_offset` (+15 °C); else your filament table | Your answers, 24 Nov |
| Tilted or inverted insert | A warning and no insert command (`W_TILTED`, `W_INVERTED`). A vertical hole in a surface that is not flat is still refused (`E_SURFACE`) | Your answer, 24 Nov |
| Magazine capacity | A profile variable, `magazine_capacity`, TBD until measured. Rule 9 refuses a print with more inserts | Your answer, 24 Nov |
| Hold-down warning | Two TBD profile variables: `min_contact_area` (mm²) and `max_height_ratio` (height ÷ √area). Warn when a part fails either | Your answer, 24 Nov |
| Insert errors | With `on_error: skip` a failing insert is left out and named in a comment, as nuts are. An export with any errors raises a pop-up warning once it finishes, built for nuts in wheel 0.2.5 | Your answer, 24 Nov; DECISIONS.md #40 |
| Panel layout | A Machine settings tab for the heat-set tool's hardware values, apart from the process settings | Your suggestion, 24 Nov |
| Insert size | One per tool, in the tool profile | Spec |
| Routine | The spec's eleven steps, header, preheat, blocks, rehearse mode | Spec |
| Where code goes | `heatsetcore` beside `nutcore`; Orca glue in `nut_inserter`; RRF macros under `macros/heatset/` | Spec |
| Grouping | One block per insertion point, nearest-neighbour order. A nut block due at the same point goes first | Spec, and revision 1 |

## RepRapFirmware design

The spec gives RRF one paragraph: macro files with the same command names, called with
`M98 P"heatset/<name>.g"`, letters that avoid G, M, N, T and P, `G38.2 K<probe>` for a bounded probe
and `G38.3` to push A. This section fills that in from the Duet3D G-code dictionary and meta-command
reference, read on 24 Nov.

**What RRF makes simpler:**

- **The probe is bounded.** `G38.2 K<probe> Z<limit>` stops at the limit and reports an error if the
  float never trips. The spec's Klipper guard "PROBE has no travel limit" does not arise.
- **The push is one line.** G38 accepts any axis, A included. `G38.3 K<probe> A<target>` feeds the
  follower until the float trips or the target is reached. The resist-and-wait logic loops inside
  `push.g`, so the G-code carries one line instead of 26 `_HS_PUSH_TICK` lines.
- **Macros act on what they measure.** RRF meta commands (`if`, `while`, `var`, `global`, `set`,
  `echo`) run inside a macro, so Klipper's render-before-run and no-loop workarounds are not needed.
- **No frame trap.** G38 targets are user coordinates, after tool offsets, and the trip height reads
  straight from `move.axes[2].userPosition`.

**What it needs:**

- **RepRapFirmware 3.6.0 or later**, which your printer runs (3.6, standalone). `G38.x F` (a
  probing speed per move) arrived in 3.6.0. Without it, every G38 move runs at the probe's one
  `M558` speed, but the pad probe (2.0 mm/s), the push (0.5 mm/s) and the press (1.0 mm/s) need
  three. Macro parameters and variables need 3.3, and `T T{expression}` needs 3.4.
- **Abort becomes a question.** RRF's `abort` ends the whole print, and after a pause and resume
  the print's own moves would run on with the tool where it stopped. So `fail.g` stays in place
  with the throat at standby (`M568 P<tool> A1`) and asks with a blocking `M291`: go on without
  the insert, lifting clear, or stop the print (DECISIONS.md #48).
- **Preheat without selecting the tool:** `M568 P<tool> S<temp> A2` heats the heat-set tool to its
  active temperature while the print tool keeps printing.
- **Tool save and restore:** `begin.g` stores `state.currentTool` in a global, and `end.g` selects it
  again with `T T{global.hs_prev_tool}`.
- **The count persists** through `echo >"heatset/count.g" ...`, run from `config.g` at start-up. RRF
  has no `SAVE_VARIABLE`.
- **Skipping a cancelled object.** RRF reads object labels from M486 commands or from the slicer's
  `; printing object` comments. `insert_start.g` checks the object's entry in `job.build.objects`.
  Whether the name or the index is the reliable key is to be confirmed with `M486`, which lists the
  objects, on the printer.
- **Hard limits** live in `/sys/heatset/limits.g` as globals, never in G-code, with the spec's
  values: 290 °C, 8 mm per push, 2 mm per unsheath, 10 s waits, 5 mm/s probe and press speeds.
- **Where the files go:** `macros/heatset/*.g` in the repository, installed to `/sys/heatset/` on the
  printer, because `M98` resolves a relative name against `/sys`.

**Emitted lines.** Each spec command becomes one `M98` call. RRF hands each extra letter to the
macro as `param.<letter>`. The letters avoid G, M, N, T and P, as the spec asks. They also avoid R,
which `M98` uses itself, and A, the follower axis. Speeds keep the spec's mm/s with one decimal,
under V, so they cannot be mistaken for RRF's F in mm/min. `G0` lines stay as they are. Proposed:

| Spec command | RRF line |
| --- | --- |
| `HEATSET_CONFIG` | `M98 P"heatset/config.g" K"<key>" H<tool> D<p> O<delta> U<surface_tol> W<temp_window> Q"<on_proud>" B"<mode>" L<rehearse_lift>` |
| `HEATSET_REQUIRE` | `M98 P"heatset/require.g" K"<key>" C<total_inserts> S<temp>` |
| `HEATSET_PREHEAT` | `M98 P"heatset/preheat.g" S<temp>` |
| `HEATSET_BEGIN` | `M98 P"heatset/begin.g" K"<key>" S<temp> Z<z_safe> C<n>` |
| `HEATSET_INSERT_START` | `M98 P"heatset/insert_start.g" I<i> O"<object>" X<x> Y<y> Z<z_top>` |
| `HEATSET_PROBE` | `M98 P"heatset/probe.g" V<probe_speed>` |
| `HEATSET_Z` | `M98 P"heatset/z.g" H<height> V<speed>` |
| `_HS_PUSH_START`, the ticks, `_HS_PUSH_END` | `M98 P"heatset/push.g" D<push> V<push_speed> W<resist_wait> C<resist_retries>` |
| `HEATSET_UNSHEATH` | `M98 P"heatset/unsheath.g" D<L> V<unsheath_speed>`, only when L > 0 |
| `HEATSET_RETRACT` | `M98 P"heatset/retract.g" D<r> V<retract_speed>` |
| `HEATSET_PRESS` | `M98 P"heatset/press.g" V<press_speed> W<press_dwell> U<flush_tol> L<press_guard>` |
| `HEATSET_INSERT_DONE` | `M98 P"heatset/insert_done.g"` |
| `HEATSET_END` | `M98 P"heatset/end.g"` |

The emitter doubles any `"` inside a string value, as RRF requires. The spec's worked example in this
form, proposed as the RRF golden file (same inputs: defaults with every TBD placeholder, PETG at
245 °C, tool 3, one insert on `bracket_1` at X 120, Y 80, `z_top` 12.4, `end_of_print`):

```gcode
; HEATSET block 1: end_of_print, inserts=1, key M3x5.7
M98 P"heatset/begin.g" K"M3x5.7" S245 Z17.400 C1
; insert 1/1 bracket_1 X120.000 Y80.000 Ztop12.400
M98 P"heatset/insert_start.g" I1 O"bracket_1" X120.000 Y80.000 Z12.400
G90
G0 Z17.400 F600
G0 X100.000 Y80.000 F9000
G0 Z14.800 F300
M98 P"heatset/probe.g" V2.0
M98 P"heatset/z.g" H3.000 V5.0
G0 X120.000 Y80.000 F1800
M98 P"heatset/z.g" H0.800 V5.0
M98 P"heatset/push.g" D5.400 V0.5 W2.0 C3
M98 P"heatset/unsheath.g" D0.300 V1.0
M98 P"heatset/retract.g" D0.300 V2.0
M98 P"heatset/z.g" H2.600 V5.0
G0 X100.000 Y80.000 F1800
M98 P"heatset/press.g" V1.0 W3.0 U0.100 L0.300
M98 P"heatset/z.g" H3.000 V5.0
M98 P"heatset/insert_done.g"
M98 P"heatset/end.g"
```

The header becomes `M98 P"heatset/config.g" K"M3x5.7" H3 D0.400 O0.000 U0.500 W5 Q"warn"
B"normal" L10.000` and `M98 P"heatset/require.g" K"M3x5.7" C1 S245`. Every number traces to the
profile, the model or a formula, as the spec requires. `push_step`, the tick count and rule 4 only
matter for Klipper.

## Found in a real Orca export

`tests/data/sample.gcode` was exported from OrcaSlicer 2.5.0 with the Klipper flavor. No export
with your RRF printer profile is available yet. Until there is one, the rules are tested on this
file and on variants made from it: comment labels only, which is how RRF reads labels, and M486
labels. A real RRF export should confirm them when you can make one.

1. **Blocks would run inside an object label.** Orca ends a layer like this: the last extrusion,
   `; stop printing object ...`, `;LAYER_CHANGE`, then the retract, the wipe and, for Klipper,
   `EXCLUDE_OBJECT_END`. Both firmwares skip the moves of a cancelled object while it is current.
   RRF's M486 "ignores G0-G3 moves in XYZ"; Klipper's exclude_object ignores every move, macro
   moves included. The nut export as built writes its block right after the last extrusion, which
   is inside the object in both firmwares. The spec's "before the next `;LAYER_CHANGE`" is inside
   the Klipper label. If that object is cancelled mid-print, the routine's moves are dropped while
   its macros still run. `insert_start.g`'s skip only covers the insert's own object.

   **Done:** every block goes after the retract and wipe that follow the layer's last extrusion,
   and after any label that ends an object (`; stop printing object`, `M486 S-1`,
   `EXCLUDE_OBJECT_END`), before anything that starts the next layer or the end G-code. The print
   tool has then retracted and wiped, and no object is current. `nutcore/gcode/place.py` does
   this for nut blocks since wheel 0.2.4 (DECISIONS.md #39), and heat-set blocks will use it too.
2. **Preheat can use the slicer's time estimate.** The sample has 134 lines of
   `M73 P<percent> R<minutes left>`, and RRF supports `M73 R`. `preheat.g` goes at the last `M73`
   line whose R exceeds the R at the block by at least `preheat_lead`, rounded up to whole minutes.
   This settles the spec's "to confirm where the export step can read them". `preheat_layers` stays
   the fallback.
3. **Object names are in the file:** Klipper's `EXCLUDE_OBJECT_DEFINE NAME=... POLYGON=[...]`, and
   the label comments that RRF reads. `O"<object>"` comes from the label of the object whose
   outline contains the insert's X, Y.
4. **The header can be placed without relying on comments:** before the first object label, after
   the start G-code. Without labels, before the first move that changes Z.
5. **The print temperature is in the file** as `M109 S220` and in `PRINT_START EXTRUDER=220`. An RRF
   export may set it with `G10 P<tool> S<temp>` or `M568` instead. The parser reads all four
   (`M104`, `M109`, `G10`, `M568`) per tool. Where none appears, the spec's filament table is the
   fallback, using `filament_type` through `ctx.config_value`. That key is in the sample's config
   block.

## Still open

No questions are open. For later: an Orca export of a test part with your RRF printer profile,
saved as `tests/data/sample_rrf.gcode`, to confirm the placement rules on real RRF output.

## Architecture

```
Orca model --(nut_inserter.adapter)--> ModelSnapshot, now with object names
ModelSnapshot + settings --(nutcore.pipeline.detect)--> nut records
ModelSnapshot + settings --(heatsetcore.detect)-------> insert records
    both go into one Report; each record carries kind "nut" or "heatset"
Report --> panel, Nuts tab, slice gate, export step
export: G-code --(nutcore.gcode.inject)--> nut blocks --(heatsetcore)--> header, preheat, blocks
```

| Module | Job |
| --- | --- |
| `heatsetcore/profile.py` | Profile schema, defaults, the TBD list, rules 1–6 and 9, derived values |
| `heatsetcore/routine.py` | Routine math: L, push, ticks, the heights table |
| `heatsetcore/insert.py` | Find `HEATSET_` bodies; insert frame (normals binned by area) and class |
| `heatsetcore/hole.py` | Hole axis and diameter, rim, bottom, depth, wall, surface |
| `heatsetcore/checks.py` | Rule 7 per insert as findings; the hold-down warning |
| `heatsetcore/place.py` | Header, preheat and block positions, `z_safe`, object names, keep-out (rule 8), the empty-hole proof |
| `heatsetcore/emit.py` | One template set per firmware: RepRapFirmware now, Klipper later |
| `nutcore` | Shared: naming (a second marker), mesh, rays, the G-code parser (temperatures per tool), the report (`kind`) |
| `nut_inserter` | Settings schema 2 and migration, a check that runs both, the gate, export composition, panel, tab |

`heatsetcore` follows the `nutcore` rules: plain Python and numpy, no `orca` import, tests that run
without Orca. Nothing new is imported while Orca loads the plugin module. No new `orca` call is
needed beyond `object.name`, which the probe found.

## Settings

Schema 2 adds a `heatset` section beside `settings` and `nuts`:

```json
"heatset": {
  "profiles": [{
    "name": "Concept D",
    "firmware": "reprapfirmware",
    "insert_key": "M3x5.7", "insert_length": 5.7, "insert_od": 4.6,
    "rest_recess": 0.0, "pad_dx": 20.0, "pad_dy": 0.0, "pad_drop": 0.4,
    "insert_temp": null, "insert_temp_offset": 15,
    "magazine_capacity": 12, "min_contact_area": 100.0, "max_height_ratio": 3.0,
    "tbd": ["rest_recess", "pad_dx", "pad_dy", "pad_drop", "block_r", "block_clearance",
            "trip_overtravel", "float_travel", "trip_force", "tool", "magazine_capacity",
            "min_contact_area", "max_height_ratio"]
  }]
}
```

The example shows a few of the spec's variables; the profile holds all of them. Its `firmware`
defaults to `reprapfirmware` rather than the spec's `klipper`, spelled as the nut settings spell it
rather than the spec's `rrf`.

- A body named `HEATSET_<key>` uses the profile whose `insert_key` is `<key>`. No such profile is
  `E_NAME_UNKNOWN`, as for nuts. Profile keys may contain a dot (`M3x5.7`); nut keys may not.
- Every variable holds a number. `tbd` lists the ones not yet measured, which hold the spec's
  placeholders. Entering a value in the panel takes it off the list. In normal mode, inserts in
  the model with anything on the list fail the slice gate, naming the variables. Rehearse mode runs.
- `insert_temp` is the panel's manual override: `null` (blank) means automatic. Automatic is the
  print tool's target temperature in the G-code plus `insert_temp_offset`, which puts the spec's
  "print temperature + 10–20 °C" into a number. A file that sets no temperature falls back to
  your filament table (PLA 225, PETG 245, ABS and ASA 265), using `filament_type`.
- `magazine_capacity`, `min_contact_area` and `max_height_ratio` are new, and TBD until measured.
  The hold-down placeholders (100 mm², 3.0) are guesses, like every TBD placeholder.
- Migrating schema 1 to 2 adds the default profile and changes nothing else. `state.read_config`
  runs it. Today a schema mismatch makes `read_config` fall back to the defaults, and the next save
  from the panel would overwrite your tuned nut ranges.

## Detection

For each `HEATSET_` body, per copy on the plate:

1. **Insert frame.** Bin the body's triangle normals by direction, folding each direction together
   with its opposite, and sum the areas per bin. The end caps are flat, so their pair normally has
   the largest total. Accept the first direction along which the body measures `insert_length` and
   around which its largest radius is half of `insert_od`, each within `body_tolerance_mm`. No match
   is `E_BODY_SIZE`. The axis line runs through the area-weighted centre of the cap triangles.
2. **Class.** `UPRIGHT` when the axis is within `axis_tolerance_deg` of vertical and the hole opens
   upward at its rim. `INVERTED` when the hole's top end is a ceiling and it opens downward. `TILTED`
   otherwise. The last two are warnings and get no insert command: install by hand.
3. **Hole axis and diameter.** From five points along the body's axis, cast 16 rays outward from
   each. Fit a circle to the hits by least squares, then cast again from the fitted centre. The
   centre is the hole axis and gives X and Y; a body modelled off-centre is placed in the hole's
   centre, with `N_OFF_CENTRE`. A direction with no wall is `E_NO_POCKET`.
4. **Rim and bottom.** Walk up and down from the middle of the insert with radial rays, as
   `pocket._rim` does. Going up, a wall counts while it lies within the hole radius plus 1.0 mm, so
   an entry chamfer belongs to the hole and a neighbouring wall does not. Going down, the hole ends
   where its radius changes by more than 0.2 mm: a floor, a step to a screw hole, or the underside
   of a through hole.
5. **Wall.** From each wall hit, cast on outward; the distance to the next surface is the wall
   there. The smallest one is checked.
6. **Surface.** Cast down onto a ring around the hole at the rim; the fitted plane must face +Z
   within 0.5°.
7. **Height.** `z_top` is the body's top. The rim is recorded beside it for the later check.
8. **Covered later.** Something modelled over the hole, with a gap above the rim, does not stop an
   `after_layer` insert, which your integration plan allows. It gets `N_COVERED`; with
   `end_of_print` the keep-out rule refuses it.

**Why not `flat_faces`.** A nut's frame comes from `flat_faces`, which seeds each direction from
the largest remaining triangle and stops after 40 directions (DECISIONS.md #31). A cylinder's side
triangles are larger than its cap triangles, so the caps are never grouped. A scratch prototype on
24 Nov confirmed it: `flat_faces` returned a side facet, 90° off, for every test body. Binning by
area found the axis within 0.001° on plain, bored, knurled, short and long bodies, each tilted, in
0.6–3 ms. An area-weighted normal tensor also works, except when the length equals the diameter.

**Accuracy and time.** The spec relies on flat faces tessellating exactly; the hole diameter is a
curved face. A faceted hole measures low by up to twice the STEP import's linear deflection. The
prototype measured 13 µm on a 32-facet Ø4 hole and under 4 µm at 64 facets, with the centre exact.
The axis and a two-pass hole fit took under 10 ms together, well inside the 100 ms event budget.

## Checks

| Rule | Fails when | Level | Code |
| --- | --- | --- | --- |
| 7, diameter | Hole outside `hole_d_min`–`hole_d_max` | Error | `E_HOLE_DIAMETER` (new) |
| 7, depth | Blind hole shallower than `insert_length + hole_extra_depth` | Error | `E_DEPTH` |
| 7, wall | Wall thinner than `min_wall` | Error | `E_WALL` (new) |
| 7, surface | Surface around the hole not facing +Z within 0.5° | Error | `E_SURFACE` (new) |
| 7, orientation | Axis not vertical, or the hole opens downward | Warning, no insert command | `W_TILTED`, `W_INVERTED` (new) |
| 7, empty hole | Plastic printed in the hole (export) | Error | `E_POCKET_NOT_EMPTY` |
| 8, keep-out | Something printed in a tool footprint before the block (export) | Error | `E_KEEP_OUT` (new), naming the blocked side |
| 9, magazine | More inserts in the print than the magazine holds | Error | `E_MAGAZINE` (new) |
| 1–6, profile | A profile rule broken, or a TBD left in normal mode | Error, at the slice gate | `E_PROFILE` (new), naming the rule |
| Hold-down | A small or tall part under `trip_force` | Warning | `W_HOLD_DOWN` (new) |
| Body | Wrong size, still a printing part, unknown key | Error | `E_BODY_SIZE`, `E_NOT_MODIFIER`, `E_NAME_UNKNOWN` |
| Off-centre | Body axis more than 0.1 mm from the hole axis | Note | `N_OFF_CENTRE` |
| Covered later | Printed over after it goes in (`after_layer`) | Note | `N_COVERED` (new) |

Keep-out only matters for `end_of_print`. When printing by layer, nothing above `z_top` exists yet
at an `after_layer` block.

## Export

1. The nut injection runs first, as built. `heatsetcore` then works on its output.
2. Lines go where findings 1 to 4 say. The insert layer is the local layer whose top is the snapped
   `z_top`.
3. The empty-hole proof uses a circle, `crosses_circle`. The nut proof's rectangle cannot be reused:
   a square of half-width `r − PROOF_INSET` has its corners outside the hole, where the hole's own
   perimeter runs.
4. `z_safe`, nearest-neighbour order and number formats follow the spec. The firmware's template set
   is chosen from the profile's `firmware`.
5. A file that already has the `; HEATSET profile` header is left alone, as `;NUT_INSERT_BEGIN`
   is for nuts. Orca may run the step twice.
6. In rehearse mode only the mode value changes in the output.

## Panel and Nuts tab

- **Panel tabs**, as you suggested: **Nuts** (the nut library, as now), **Heat-set** (the spec's
  Process and Behaviour groups, the hole limits, timing, the normal/rehearse switch, and the
  manual temperature override with the automatic value beside it), and **Machine settings** (the
  heat-set tool's hardware: the spec's Measured and Motion groups, the tool number, firmware and
  magazine capacity). TBD values carry a badge, derived values are read-only, and validation
  messages name the rule. The Activity list stays at the bottom.
- **Nuts tab:** insert points with both tool footprints, mouth over the hole and pad over the hole,
  as your integration plan asks.

## Tests

The spec's own tests stand, with RRF first: each profile rule broken in turn, the routine math, the
RRF golden file byte for byte, rehearse differing only in the mode value, placement on a real export,
and the checks. In addition:

| Case | Setup | Expected |
| --- | --- | --- |
| H1 | Insert flush in a Ø4.0 × 6.7 blind hole | `UPRIGHT`, ok, placement on the hole axis, `z_top` at the body's top |
| H2 | H1, object rotated 30° about Z and moved | ok, placement follows the object |
| H3 | Body 0.15 mm off the hole axis | Placement unchanged, `N_OFF_CENTRE` |
| H4 | Hole Ø4.3 | `E_HOLE_DIAMETER`; message contains 4.30, 3.90 and 4.20 |
| H5 | Blind hole 6.5 deep | `E_DEPTH`, 6.70 needed |
| H6 | Ø4.0 to 7.0 deep, then Ø3.4 through | ok, depth to the step |
| H7 | Through hole 6.0 deep | ok: the depth rule is for blind holes |
| H8 | 0.5 mm entry chamfer | ok, rim at the top face |
| H9 | Object tilted 20° about X | `W_TILTED`, no placement |
| H10 | Hole in the underside | `W_INVERTED`, no placement |
| H11 | Wall 1.0 mm | `E_WALL` |
| H12 | Surface sloped 5° around a vertical hole | `E_SURFACE` |
| H13 | Instance scaled by 1.02 | `E_BODY_SIZE` |
| H14 | Mirrored instance; two instances | As H1; two records |
| H15 | Body still a printing part | `E_NOT_MODIFIER` |
| H16 | `HEATSET_M4x8` with no such profile | `E_NAME_UNKNOWN` |
| H17 | A lid over the hole with a gap | ok, `N_COVERED` |
| H18 | 720-facet knurled body in a 256-facet hole | ok, under 100 ms |
| H19 | Plain, bored and knurled bodies, and length equal to diameter, each tilted | Axis found every time |
| H20 | A part 8 × 8 mm on the bed and 30 mm tall | `W_HOLD_DOWN` |
| P1 | RRF variant, one insert, the nut pocket used as the hole | Header before the first object label; block after the layer's retract, wipe and object-end label |
| P2 | RRF variant, `end_of_print` | Block after the last object-end label, before the end G-code |
| P3 | RRF variant, `preheat_lead` 120 s | `preheat.g` at the last `M73` whose R is at least 2 above the block's |
| P4 | P3 with the `M73` lines removed | Preheat `preheat_layers` layers earlier |
| P5 | No object labels | Block after the retract and wipe, before the next layer's first Z move |
| P6 | RRF variant | `O"..."` holds the label of the object around the insert |
| P7 | Plastic in the hole; then only the hole's own perimeter | `E_POCKET_NOT_EMPTY`; then ok |
| P8 | `end_of_print`, a taller wall within `block_r` | `E_KEEP_OUT`, naming the side |
| P9 | Three inserts on one layer | One block, nearest-neighbour order from the last toolhead position |
| P10 | A nut and an insert due at the same point | Nut block, then heat-set block |
| P11 | `M109 S220`; `G10 P0 S220`; none and PETG; a profile value | `S235`; `S235`; `S245`; the profile value |
| P12 | A file already processed | Left byte-identical |
| P13 | Object name containing `"` | Doubled inside `O"..."` |
| P14 | P1 to P5 on the Klipper export, `tests/data/sample.gcode` | The same positions (milestone 9) |
| P15 | More inserts than `magazine_capacity` | `E_MAGAZINE`; with `on_error: skip`, the inserts past the capacity left out, and the pop-up |
| P16 | An insert failing the empty-hole proof, `on_error: skip` | Left out with a comment; the other inserts written; the pop-up after the export |

Library and plugin cases: schema 1 migrates with every tuned nut value kept; `read_config`
migrates a stored schema-1 config without the "not usable" message; a profile round-trips through
`save_config`; the slice gate blocks on a TBD in normal mode and on an insert error.

## Milestones

The spec's milestones, with RepRapFirmware in place of Klipper, a milestone 0 for the printer tests,
and the plugin and pages added as 6. Each ends with its tests passing and a commit.

| Milestone | Build | Done when |
| --- | --- | --- |
| 0. RRF ground work (done, 0.2.4) | The RRF dry-run `macros/reprapfirmware/insert_nut.g` (check the values, report them, pause with `M226`), and nut blocks moved outside object labels (`nutcore/gcode/place.py`) | Its test keeps it in step with the nut RRF template; placement tests on the real export and its RRF variants (`tests/test_place.py`) |
| 1. Profile (done, 0.2.6) | `profile.py`, settings schema 2 and migration, the `HEATSET_` marker | Each rule broken in turn refuses; migration keeps the nut library (`tests/test_heatset_profile.py`) |
| 2. Routine math (done) | `routine.py` | Derived values, push + L = Li + e, the heights table (`tests/test_heatset_routine.py`) |
| 3. RRF emitter (done) | `emit.py`, RRF template set | The RRF golden file byte for byte (`tests/data/heatset_golden_rrf.gcode`); rehearse differs only in the mode value |
| 4. Placement (done) | `place.py`, export composition | P1–P13, P15 and P16 on the RRF variants of the real export, using hand-made insert records (`tests/test_heatset_place.py`; DECISIONS.md #45) |
| 5. Checks (done) | `insert.py`, `hole.py`, `checks.py`, `detect.py` | H1–H20 and the extra checks (`tests/test_heatset_detect.py`; DECISIONS.md #46) |
| 6. Plugin and pages (done, 0.3.0) | State, gate, export (`heatsetcore/export.py`), panel tabs, tab footprints | Plugin cases pass (`tests/test_plugin.py`, `tests/test_heatset_export.py`); wheel 0.3.0 builds (DECISIONS.md #47) |
| 7. RRF macros (written, not yet run) | `macros/heatset/*.g` and `limits.g`; install and bring-up in `macros/heatset/README.md` | Static checks pass (`tests/test_heatset_macros.py`; DECISIONS.md #48). Still to do on the printer: every macro in rehearse mode, `M37` simulation of a whole file |
| 8. Bring-up | Manual, as the spec, on the RRF printer | A rehearse run, every TBD measured, a coupon insert within `flush_tol` |
| 9. Klipper | The spec's Klipper templates, its golden file, `firmware/klipper/heatset_macros.cfg` | The spec's Klipper golden file byte for byte; P14 |

## Later

- **Insert height check**, as you asked. When the body's top is more than half a layer from the
  hole's rim, warn: the press always ends flush with the probed surface, so the model would not
  show what the printer does.
- The spec's "Not now": the Klipper Python extra, more sizes per tool, plates after the first,
  refills mid-print.

## Sources

- `docs/HEATSET_GCODE_SPEC.md`, your Word file of 23 Nov, converted on 24 Nov. Every word matches
  the original, the five code blocks are byte-identical, and the worked example's derived values
  reproduce from its formulas.
- Your "Concept D heat-set tool: software and integration plan" (23 Nov): its Slicer plugin
  section, open decisions and gaps.
- `tests/data/sample.gcode`, exported from OrcaSlicer 2.5.0 with the Klipper flavor on 10 Nov.
- Duet3D [G-code dictionary](https://docs.duet3d.com/User_manual/Reference/Gcodes) (G38.2–G38.5,
  M73, M98, M109, M486, M568, T) and
  [G-code meta commands](https://docs.duet3d.com/User_manual/Reference/Gcode_meta_commands)
  (abort, echo to a file, loops in job files, macro parameters, variables), read on 24 Nov.
- [ruthex M3 threaded insert, M3x5.7, at 3DJake](https://www.3djake.com/ruthex/threaded-insert-m3-100-pieces):
  4.6 mm outer diameter, 4.0 mm hole, 1.6 mm minimum wall.
- [Prusa, heat-set inserts M3 standard](https://www.prusa3d.com/product/heat-set-inserts-m3-standard-100-pcs/):
  the iron at the filament's print temperature plus 10–20 °C.
