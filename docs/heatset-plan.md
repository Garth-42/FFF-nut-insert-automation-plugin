# Heat-set inserts: plan

Nov 24, 2026 · proposal for review. It extends `docs/SPEC.md`, and nothing in it is built yet.
Once the decisions below are settled it becomes a "Heat-set inserts" section of the spec, and
the build follows the milestones at the end.

## Summary

Today the plugin drops square nuts into closed pockets during the print. A heat-set insert
differs in three ways that reach the code: it is round, it is pressed into a hole smaller than
itself, and it goes in through an open hole that is never covered. The plan adds a second kind
of library entry, `heatset`, with its own body measurement, hole measurement, checks,
insert-layer rule and templates. The nut path stays as it is.

Most of the plugin carries over unchanged: the snapshot and adapter, the ray caster and its
robust-distance rule, the report, notifications, the slice gate, the G-code parser, local layers, the print-order and
not-on-plate checks, insertion points, blocks, the summary and the repeat-run guard. No new
`orca` call is needed, and nothing changes about threads, files or the event budget.

## How an insert differs from a nut

| | Square nut (built) | Heat-set insert (planned) |
| --- | --- | --- |
| Body | Box: across flats × across flats × thickness | Cylinder: outer diameter × length, often knurled |
| Hole | Larger than the nut: a gap on every side | Smaller than the insert: the knurls melt into the wall |
| Goes in by | Dropping onto its seat | A hot tip pressing it to a set depth |
| Height | From the seat it settles on | From the modelled body, snapped to the printed rim |
| X and Y | Centred between the pocket walls | Centre of the hole, from a circle fit |
| Orientation | Flat, on edge or on a corner | Axis vertical, hole opening upward: the tool can only press down |
| Angle about its axis | Yaw of the flats | None: an insert is round |
| Inserted | After the last layer below the roof, then covered | After the layer that completes the hole's rim, never covered |
| Values for the macro | Position, class, yaw, feeder | Position, top and bottom, rim, length, feeder, temperature |

## Decisions for you

Each has a recommendation, and the rest of the plan assumes it.

| | Question | Recommended | Alternatives |
| --- | --- | --- | --- |
| D1 | How does the library tell an insert from a nut? | A new entry field `kind`, `nut` or `heatset`. Settings move to schema 2, and a saved schema-1 library is migrated, never replaced | Reuse `shape` with a value `heatset`: no new field, but it mixes the body's shape with the process |
| D2 | What do you name an insert body in CAD? | `HEATSET_<key>`, and `NUT_<key>` keeps working for every key. The marker is cosmetic: the entry's kind decides the process | `NUT_` only (`NUT_M3HS`): no naming change. Not `INSERT_`: ordinary bodies such as `Insert_Plate` would match, fail as `E_NAME_UNKNOWN` and block the slice |
| D3 | Where does the insert's height come from? | The body: model it in CAD where the insert should end up. X and Y still come from the hole | Always flush with the rim, whatever the body says |
| D4 | When is it pressed? | Right after the layer that completes the hole's rim. Nothing above that layer exists yet, so the hot tool cannot hit taller features | After the last layer: one tool visit for all inserts, but taller features nearby can block the tool. Could become a setting later |
| D5 | Press temperature | The print tool's own `M104`/`M109` target in the file plus a per-type offset (+15 °C by default), passed as `{press_temp}`. Prusa's guidance is the print temperature plus 10–20 °C. A macro may ignore it | A fixed temperature per type, which is wrong when one insert goes into PLA and PETG. Or the macro decides alone, which Marlin cannot: its macros take no parameters |
| D6 | An insert on a side face or the underside | Warning and no insert command: install it by hand (`W_TILTED`, `W_INVERTED`) | An error that blocks the slice |
| D7 | Nuts and inserts due at the same layer | One block, nut lines first, so each tool is picked up once | One block per kind |

## Library

Settings schema 2. `library.migrate(config)` upgrades a schema-1 document before validation:
each entry gains `kind: "nut"`, the template table moves under `templates.nut`, and the default
heat-set templates are added. `state.read_config` and the command line call it.

The migration is not optional. Today `read_config` treats any config that fails validation as
unusable and shows the defaults instead, so a schema bump on its own would hide your tuned M3SQ
ranges, and the next save from the panel would overwrite them.

A heat-set entry:

| Field | Example for `M3HS` | Meaning |
| --- | --- | --- |
| Key | `M3HS` | Bodies named `HEATSET_M3HS` (or `NUT_M3HS`) use this entry |
| Kind | `heatset` | |
| Diameter | 4.6 mm | Outer diameter over the knurls |
| Length | 5.7 mm | |
| Hole diameter | 3.90–4.10 mm | Min–max of the modelled hole |
| Hole depth | 6.2 mm or more | From the rim to the hole's floor, or to a step down to a screw hole |
| Wall | 1.6 mm or more | Plastic around the hole; less is a warning |
| Sink | 0.00–0.30 mm | How far the insert's top sits below the rim. Negative means it stands proud |
| Press temperature offset | +15 °C | Added to the print temperature |
| Feeder | 2 | Passed to the macro |

The sizes are those of a ruthex RX-M3x5.7: 4.6 mm outer diameter, 4.0 mm hole, 1.6 mm minimum
wall. The ranges, the depth (length plus 0.5 mm for displaced plastic) and the offset are
placeholders, like every number in the nut library. Replace them from test prints.

```json
{
  "key": "M3HS",
  "label": "M3 heat-set insert, 5.7 mm",
  "kind": "heatset",
  "diameter": 4.6,
  "length": 5.7,
  "feeder": 2,
  "hole": {"diameter": [3.9, 4.1], "depth_min": 6.2, "wall_min": 1.6},
  "sink": [0.0, 0.3],
  "press_temp_offset": 15
}
```

Validation follows the existing rules, except that `sink` may start at zero or below, so it
needs its own range check: `_check_range` rejects sizes that are not positive.

The templates become one table per kind:

```json
"templates": {
  "nut": {"klipper": "INSERT_NUT KEY={key} CLASS={cls} ...", "reprapfirmware": "...", "marlin": ""},
  "heatset": {
    "klipper": "INSERT_HEATSET KEY={key} X={x} Y={y} Z_TOP={z_high} Z_LOW={z_low} RIM={rim_z} LENGTH={length} TEMP={press_temp} FEEDER={feeder} TOOL={tool}",
    "reprapfirmware": "M98 P\"insert_heatset.g\" K\"{key}\" X{x} Y{y} Z{z_high} L{z_low} R{rim_z} H{length} B{press_temp} F{feeder} S{tool}",
    "marlin": ""
  }
}
```

The RepRapFirmware letters avoid G, M, N, T and P, as the nut template does.

## Name matching

`naming._PREFIX` accepts `HEATSET_` as well as `NUT_`, with the same boundaries. Both look up
the same library, and the longest key still wins. `HEATSET_M3HS`, `HEATSET_M3HS:1` and
`Bracket/heatset_m3hs (2)` match `M3HS`; `PREHEATSET_M3HS` does not. A marked body still leaves
the host, so it is never measured as a wall.

## Detection

The pipeline branches on the entry's kind in `pipeline._detect_nut`, and the nut path is
untouched. For a heat-set entry:

1. **Insert frame.** Bin the body's triangle normals by direction, folding each direction
   together with its opposite, and sum the areas per bin. The end caps are flat, so their pair
   normally has the largest total. Try directions in that order, and accept the first along
   which the body extends the library length and around which its largest radius is half the
   library diameter, each within `BODY_TOL`. The knurl tips set a detailed model's largest
   radius. The axis line runs through the area-weighted centre of the cap triangles. No match
   is `E_BODY_SIZE`.
2. **Class.** `tilt = acos(|a_z|)`. Beyond `AXIS_TOL` from vertical the insert is `TILTED`.
   There is no yaw.
3. **Hole wall.** From five points along the body's axis, cast 16 rays outward from each. Fit a
   circle to the hits by least squares: its centre is the hole's axis and its diameter the hole
   diameter. Cast once more from the fitted centre. A direction with no wall is `E_NO_POCKET`,
   naming the side. The insert is larger than its hole by design, so the sides get no
   interference check.
4. **Open end.** Cast rays straight up from a disc inside the hole, starting at the insert's top.
   All clear: `UPRIGHT`. Otherwise cast straight down from its bottom: all clear means the hole
   opens downward, `INVERTED`. Blocked both ways, wholly or in part (a ledge over the hole, a
   closed cavity), is `E_DROP_PATH`.

For an upright insert:

5. **Rim.** Walk up from the middle of the insert with radial rays, as `pocket._rim` does. A
   wall counts while it is within the hole radius plus `RIM_FLARE`, so an entry chamfer still
   belongs to the hole and a neighbouring wall does not. Starting from the middle, not the top,
   keeps the walk inside the hole when the insert is modelled proud (as DECISIONS.md #7 does for
   nuts).
6. **Bottom.** Walk down from the middle of the insert the same way. The hole ends where the
   wall leaves the hole radius ± `HOLE_TOL`: at a floor, at a step to a narrower screw hole, or
   at the underside of a through hole. Depth is rim minus bottom. A body that reaches below the
   bottom is `E_INTERFERENCE`.
7. **Wall.** From each wall hit cast on outward; the distance to the next surface is the wall
   there. The smallest one is reported.
8. **Placement.** X and Y are the hole centre. Z comes from the body: `z_high` is its top,
   `z_low = z_high − length`, and the placement point is midway. `sink = rim_z − z_high`. When
   the body's axis is more than `OFF_CENTRE` from the hole's, `N_OFF_CENTRE`.

| Constant | Default | Used for |
| --- | --- | --- |
| `HOLE_RAYS` | 16 | Radial rays per height |
| `HOLE_HEIGHTS` | 5 | Heights along the insert |
| `RIM_FLARE` | 1.0 mm | How far a chamfer may widen the hole and still count as the hole |
| `HOLE_TOL` | 0.2 mm | Change of radius that ends the hole going down |

**Why not `flat_faces`.** A nut's frame comes from `flat_faces`, which seeds each direction from
the largest remaining triangle and stops after 40 directions (DECISIONS.md #31). A cylinder's
side triangles are larger than its cap triangles, so the 40 seeds all land on the side and the
caps are never grouped. A scratch prototype run against `nutcore` on 24 Nov showed this:
`flat_faces` returned a side facet, 90° off, for every test body. Binning by area found the axis
to within 0.001° on plain, bored, knurled, short and long bodies, each tilted, in 0.6–3 ms. An
area-weighted normal tensor also works, except when the length equals the diameter, where its
three eigenvalues coincide. `faces.py` and the nut path stay as they are.

**Accuracy.** The spec relies on flat faces tessellating exactly and says no placement number
depends on a curved face. For inserts the hole diameter and centre do. A faceted hole's wall lies
between the true radius and the true radius less the STEP import's linear deflection, so the
measured diameter comes out low by up to twice that deflection. The prototype measured 1.4–1.8
times: 13 µm for a 32-facet Ø4 hole, under 4 µm at 64 facets, well inside a 0.2 mm range. The
centre came out exact. The README should ask for a fine deflection on import, and
`docs/DECISIONS.md` should record the change.

**Time.** In the prototype, the axis and a two-pass hole fit took under 10 ms together. The rim
and bottom walks take coarse steps and then bisect, as `_rim` does. A timing test keeps an
insert check under the 100 ms event budget, as `test_nut_body_with_a_round_hole_and_many_facets`
does for nuts.

## Checks

| Check | Fails when | Level | Code |
| --- | --- | --- | --- |
| Body size | Diameter or length differs from the library by more than `BODY_TOL` | Error | `E_BODY_SIZE` |
| Hole diameter | Outside the allowed range | Error | `E_HOLE_DIAMETER` (new) |
| Hole depth | Rim to bottom less than the minimum | Error | `E_DEPTH` |
| Sink | Insert top outside the allowed range below the rim; negative means proud | Error | `E_SINK` (new) |
| Open side | A direction with no wall | Error | `E_NO_POCKET` |
| Covered | Anything over the hole, unless it opens downward | Error | `E_DROP_PATH` |
| Too deep | The body reaches below the hole's bottom | Error | `E_INTERFERENCE` |
| Still printing | The body is a printing part | Error | `E_NOT_MODIFIER` |
| Tilted | Axis not vertical: install by hand | Warning | `W_TILTED` |
| Upside down | The hole opens downward: install by hand | Warning | `W_INVERTED` (new) |
| Thin wall | Wall below the minimum | Warning | `W_WALL_THIN` (new) |
| Off-centre | Body axis more than 0.1 mm from the hole's axis | Note | `N_OFF_CENTRE` |

Messages keep the existing form, which `checker.range_finding` already writes: "HEATSET_M3HS #2:
hole diameter 4.30 mm, allowed 3.90–4.10 mm. Reduce by 0.20–0.40 mm in CAD and re-export."

## Report

Report schema 2. Every record gains `kind`. For an insert, `cls` is `UPRIGHT`, `INVERTED` or
`TILTED`; `yaw_deg` and `roof_z` are null; `rim_z` is the hole's rim; `pocket` holds `diameter`,
`depth`, `wall`, `sink` and `bottom_z`; `box` is the hole as an oriented box, which the preview
draws as a cylinder; and `window` is `[rim_z, null]`. `Report.from_dict` reads a schema-1 report
as all nuts, so an old `report.json` still works with the `inject` command. The CSV gains `kind`,
`hole_diameter`, `wall` and `sink` columns.

## Export

`gcode/proof.py` gains `plan_insert` beside `plan_pocket`:

1. **Footprint.** A circle: the hole's centre and radius. Local layers are the extrusion within
   `PROOF_RING` of it. The proof needs a new `crosses_circle`, the distance from the centre to
   each segment. The rectangle test cannot be reused: a square of half-width `r − PROOF_INSET`
   has its corners outside the hole, where the hole's own perimeter runs, so every hole would
   fail.
2. **Open layers** are those whose middle lies between the hole's bottom and its rim, proved
   empty as for nuts. In addition, nothing may cross the circle in any layer above the rim:
   support or another part over the hole would be printed onto the insert. Both are
   `E_POCKET_NOT_EMPTY`, with a message for each.
3. **Snap.** The printed rim is the top of the last open layer. `z_high` is the printed rim less
   the modelled sink, and `z_low = z_high − length`. `E_PRINTED_DEPTH` when the printed hole is
   shallower than the minimum.
4. **Insert layer.** The last open layer: the one that completes the rim. The insertion point,
   the print-order checks, `N_NOT_ON_PLATE` and `on_error` work as they do for nuts.
5. **Temperature.** The parser remembers each tool's last `M104`/`M109` `S` target, for the tool
   in the `T` word when there is one, else the active tool. `{print_temp}` is the active print
   tool's target at the insertion point, and `{press_temp}` adds the entry's offset. Both are −1
   when the file sets no temperature, as when temperatures go to a start macro. The sample export
   has `M109 S220`.
6. **Blocks.** Nuts and inserts due at the same point share one block, nut lines first. Summary
   lines name the insert: `; nut 3 HEATSET_M3HS UPRIGHT X... Y... Z_TOP... after layer_z=...`.

Optionally, the export step reads `xy_hole_compensation` and `hole_to_polyhole` through the
existing `ctx.config_value` and writes them in the summary. Both keys appear in the config block
of the sample export and both change the printed hole, so a hole that prints the wrong size can
be traced to its preset.

## Templates and the macro

New placeholders for heat-set templates:

| Placeholder | Value |
| --- | --- |
| `{kind}` | `heatset` |
| `{cls}` | `UPRIGHT` |
| `{z_high}` | Insert top when pressed home, as printed: the printed rim less the sink |
| `{z_low}` | Insert bottom: `z_high` less the length |
| `{z}` | Midway between them |
| `{rim_z}` | The hole's rim, as printed |
| `{length}` `{diameter}` | From the library |
| `{print_temp}` | The active print tool's last `M104`/`M109` target, or −1 |
| `{press_temp}` | `{print_temp}` plus the entry's offset, or −1 |

Shared with nuts and unchanged: `{index}` `{key}` `{x}` `{y}` `{feeder}` `{layer_z}` `{tool}`
`{rx}` `{ry}` `{rz}`. A template is checked against its own kind's list when the settings are
saved and again at export, so `{yaw}` in a heat-set template is `E_TEMPLATE`.

What the macro must do: the same contract as `INSERT_NUT` (the print tool arrives hot and not
retracted, and goes back to the same place, primed, with modes unchanged), and for the insert:

- heat the tip to `TEMP`, or to the print tool's target plus an offset when `TEMP` is −1;
- pick an insert from `FEEDER` and move above `X`, `Y`;
- lower until the insert meets the rim, with the tip at about `RIM + LENGTH`;
- press slowly about 90 % of the way, finish to `Z_TOP`, and lift clear without pulling the
  insert back up. CNC Kitchen recommends melting about 90 % of the way and pushing the rest.

Add `macros/klipper/insert_heatset_dry_run.cfg`, which follows the nut dry run: check the values,
report them, pause. A test keeps it in step with the Klipper template, as one already does for
`INSERT_NUT`.

## Panel and Nuts tab

- **Panel.** A Kind column in the library table; Add nut and Add insert buttons; the entry form
  shows its kind's fields (`NUT_FIELDS` or a new `HEATSET_FIELDS`); templates in two groups, each
  with its placeholder list; the macro contract for both; the Modifier reminder names insert
  bodies too.
- **Nuts tab.** An insert's hole is drawn as a cylinder (two circles and four lines) with the
  same crosshair and axis arrow. List rows read "UPRIGHT, hole Ø4.02" instead of a yaw, and the
  detail shows diameter, depth, wall and sink.

## What changes, file by file

| File | Change |
| --- | --- |
| `src/nutcore/library.py` | Schema 2, `migrate`, `kind`, an `InsertType`, validation per kind, the default M3HS entry, templates per kind |
| `src/nutcore/naming.py` | The `HEATSET_` marker |
| `src/nutcore/insert.py` (new) | Insert frame (normals binned by area) and class |
| `src/nutcore/hole.py` (new) | Hole wall, open end, rim, bottom, wall, placement |
| `src/nutcore/checker.py` | `check_insert` |
| `src/nutcore/pipeline.py` | `_detect_nut` branches on kind |
| `src/nutcore/report.py` | `kind`, schema 2, reading schema 1, CSV columns |
| `src/nutcore/gcode/parser.py` | Temperature per tool |
| `src/nutcore/gcode/proof.py` | `crosses_circle`, `plan_insert` |
| `src/nutcore/gcode/templates.py` | Placeholder lists per kind |
| `src/nutcore/gcode/inject.py` | Template per kind, insert values, block order |
| `src/nutcore/cli.py` | Migrate a `--config` file on load |
| `src/nut_inserter/state.py` | Migrate in `read_config` |
| `src/nut_inserter/ui_panel.py`, `ui_preview.py` | As above |
| `macros/klipper/insert_heatset_dry_run.cfg` (new) | Dry-run macro |
| `tests/builders.py` | `cylinder`, `insert`, `hole_block`, `gcode_hole` |
| `docs/` | Spec section, DECISIONS, README, manual-test |

Unchanged: `adapter.py`, `__init__.py`, `permissions.py`, `mesh.py`, `faces.py`, `rays.py` and
`frame.py`; `pocket.py` too, unless `hole.py` shares its rim walk. Six lines of the existing tests
name the template path or a schema number and change with schema 2; nothing else in the 91
tests should.

## Tests

New builders:

- `cylinder(diameter, length, centre, rot, sides=64)`: a faceted cylinder with end caps.
- `insert(key="M3HS", centre, rot, sides)`: a cylinder of the library size named
  `HEATSET_<key>`.
- `hole_block(hole=4.0, depth=6.7, sides=64, wall=3.0, through=False, step=None, chamfer=None,
  ledge=None)`: a faceted tube for the hole wall, a floor or step disc, and an outer box. Like
  `pocket_block`, it need not be watertight.
- `gcode_hole(...)`: layers of circular perimeters around the hole, solid below the floor, with
  options for fill inside, something over the hole above the rim, arcs, and `M104`/`M109` lines.

Detection cases, all with the M3HS placeholder entry:

| Case | Setup | Expected |
| --- | --- | --- |
| H1 | Insert flush in a Ø4.0 × 6.7 blind hole | `UPRIGHT`, ok, placement on the hole axis, `z_high` at the rim |
| H2 | H1, object rotated 30° about Z and moved | ok, placement follows the object |
| H3 | Body 0.15 mm off the hole axis | Placement unchanged, `N_OFF_CENTRE` |
| H4 | Hole Ø4.3 | `E_HOLE_DIAMETER`; message contains 4.30, 3.90 and 4.10 |
| H5 | Hole 5.9 deep | `E_DEPTH` |
| H6 | Insert top 0.2 mm above the rim | `E_SINK` |
| H7 | Ø4.0 to 7.0 deep, then Ø3.4 through | ok, depth measured to the step |
| H8 | Through hole | ok |
| H9 | 0.5 mm entry chamfer, insert flush with the top face | ok, rim at the top face |
| H10 | Object tilted 20° about X | `W_TILTED`, no placement |
| H11 | Hole in the underside, opening downward | `W_INVERTED`, no placement |
| H12 | Wall 1.0 mm | `W_WALL_THIN` |
| H13 | Ledge over a third of a blind hole | `E_DROP_PATH` |
| H14 | Instance scaled by 1.02 | `E_BODY_SIZE` |
| H15 | Mirrored instance; two instances | As H1; two records |
| H16 | Body deeper than its hole | `E_INTERFERENCE` |
| H17 | Body still a printing part | `E_NOT_MODIFIER` |
| H18 | 720-facet knurled body in a 256-facet hole | ok, under 100 ms |
| H19 | Bodies: plain 64 facets, bored, knurled, length equal to diameter, each tilted | Axis found every time; a guard against using `flat_faces` here |

Name cases: `HEATSET_M3HS`, `HEATSET_M3HS:1`, `Bracket/heatset_m3hs (2)` and `NUT_M3HS` match
`M3HS`; `PREHEATSET_M3HS` does not.

G-code cases:

| Case | Setup | Expected |
| --- | --- | --- |
| HG1 | Perimeters around the hole, nothing above the rim | Block after the last move of the rim layer; `Z_TOP` is that layer's top less the sink |
| HG2 | Fill inside the hole | `E_POCKET_NOT_EMPTY` |
| HG3 | Extrusion across the hole above the rim | `E_POCKET_NOT_EMPTY` |
| HG4 | Rim half a layer off the layer boundaries | `Z_TOP` snaps to the printed rim |
| HG5 | Hole perimeter written as arcs | Proof passes |
| HG6 | A nut and an insert due at the same layer | One block, nut line first |
| HG7 | Each firmware's heat-set template | Exact expected text |
| HG8 | `M109 S220` and offset 15; then no temperature in the file | `TEMP=235`; then `TEMP=-1` |
| HG9 | A heat-set template using `{yaw}` | `E_TEMPLATE` |

Library and plugin cases:

- A schema-1 config migrates with every tuned value kept, and validates.
- A heat-set entry validates; a sink range whose minimum exceeds its maximum, and an unknown
  kind, are rejected.
- `read_config` migrates a stored schema-1 config, with no "not usable" message.
- `save_config` round-trips a heat-set entry.
- The slice gate blocks on an insert error and passes with `on_error` set to `skip`.

## Milestones

Each ends with its checks passing and a commit.

| Milestone | Build | Done when |
| --- | --- | --- |
| H0. Approve | Settle D1–D7; fold this plan into `docs/SPEC.md` | You sign off |
| H1. Library and names | Schema 2, `migrate` (library, `read_config`, CLI), the `HEATSET_` marker | Library and name cases pass, and the existing tests with the six lines updated |
| H2. Detection | `insert.py`, `hole.py`, `check_insert`, the pipeline branch, report schema 2 | H1–H19 pass |
| H3. Export | `crosses_circle`, `plan_insert`, temperatures, templates per kind, shared blocks | HG1–HG9 pass |
| H4. Plugin and pages | Panel and Nuts tab for both kinds | Plugin cases pass; wheel 0.3.0 builds |
| H5. Macro and docs | Heat-set dry-run macro, README, manual-test | Macro test passes |
| H6. In Orca and on the printer | The checks below | Results recorded in `docs/manual-test.md` |

## Manual checks

- [ ] **Upgrade.** Remove 0.2.3, install 0.3.0 and add Nut insert to the process preset again.
  Expect your M3SQ library as you tuned it, plus the M3HS entry.
- [ ] **Insert A.** A test block with a Ø4.0 × 6.7 hole and a `HEATSET_M3HS` body flush with its
  top. Expect `E_NOT_MODIFIER` until the body is a Modifier, then `UPRIGHT` and ok. Rotate the
  block 90° about X: `W_TILTED`.
- [ ] **Insert C.** The Nuts tab draws the hole as a cylinder in the right place.
- [ ] **Insert D.** Export: one `INSERT_HEATSET` line after the layer that completes the rim,
  with `Z_TOP` at that layer's top.
- [ ] **Hole size.** Print the test block with your process preset, try an insert by hand, and
  set the hole range from what fits.
- [ ] **Insert E.** A dry run on the printer with `insert_heatset_dry_run.cfg`, then one real
  insert into a test block.

## Risks

- **Printed holes differ from CAD.** Holes come out small, and Orca's X-Y hole compensation and
  polyhole options change them further. The plugin measures the model, so set the hole range
  from test prints made with the same process preset.
- **Displaced plastic.** Melt can rise in a ring around the insert while later layers print
  nearby. A small sink (0.1–0.3 mm) and Z hop keep the nozzle clear.
- **A hot tip in a part mid-print.** Heat spreads into fresh layers. Speed, dwell and
  temperature belong to the macro; prove them on a test block first.
- **Press force.** Pressing needs bed adhesion, and a thin boss can flex. The wall warning reads
  the model; the printed wall is the wall loops plus infill.
- **Pick-up and release.** The tip must carry the insert down and leave it behind on the way up.

## Out of scope

- Pressing sideways or from below: a warning, and you install by hand.
- Flanged inserts, whose flange sits on the surface.
- A hole made by an Orca negative volume: the hole must be in the model, because the rays see
  only printing parts.
- Cold press-fit or ultrasonic inserts. They could reuse this path without the heat.
- Checking for tool collisions when pressing after the last layer.
- Tapered holes beyond what the diameter range absorbs.

## Sources

Read on 24 Nov 2026.

- [ruthex M3 threaded insert, M3x5.7, at 3DJake](https://www.3djake.com/ruthex/threaded-insert-m3-100-pieces):
  4.6 mm outer diameter, 4.0 mm hole, 5.7 mm length, 1.6 mm minimum wall.
- [Prusa, heat-set inserts M3 standard](https://www.prusa3d.com/product/heat-set-inserts-m3-standard-100-pcs/):
  the iron at the filament's print temperature plus 10–20 °C.
- [CNC Kitchen, tips for threaded inserts in 3D printing](https://cnckitchen.com/blog/tipps-amp-tricks-fr-gewindeeinstze-im-3d-druck-3awey?format=amp):
  melt about 90 % of the depth and push the rest; printed holes come out smaller than in CAD.
