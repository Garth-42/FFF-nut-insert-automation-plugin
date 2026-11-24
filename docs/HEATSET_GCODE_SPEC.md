<!-- Converted from the Word file "Heat-set tool G-code: instructions for Claude Code" (Nov 23, 2026) on 24 Nov 2026 with pandoc. The five code blocks were copied exactly from the document's Code paragraphs. -->

# Heat-set tool G-code: instructions for Claude Code

Nov 23, 2026 · @Garth

## How to use this with Claude Code

Export this doc as Markdown and save it as docs/HEATSET_GCODE_SPEC.md in the nut-plugin repository, next to docs/SPEC.md. Start Claude Code in that repository and paste this prompt:

```text
Read docs/SPEC.md (the nut plugin) and docs/HEATSET_GCODE_SPEC.md.
Implement the heat-set insert G-code generator it describes: a pure-Python
package heatsetcore beside nutcore, the Orca glue in the existing plugin,
and the Klipper macros in firmware/klipper/heatset_macros.cfg.
Work through the milestones in "Tests and acceptance" in order.
Every number in the emitted G-code must come from the tool profile,
the model or a formula in the spec. Never invent values marked TBD.
Ask before changing any convention in the spec.
```

Values marked TBD come from the prototype. The code ships with the placeholder defaults shown. Normal export stays blocked until every TBD is set; rehearse mode runs without them.

## Goal and scope

Build the export step that writes the complete heat-set insertion routine into the G-code, with every hardware and process number taken from a tool profile set at slice time.

- **Input:** insert bodies named HSI\_\<key\> (same name rule as NUT\_\<key\>), the hole each one sits in, and the tool profile from the plugin settings.

- **Output:** a header, preheat lines and insertion blocks in the exported G-code. Each insert gets the whole routine: pad probe, hot push, unsheath, cold press and flush check.

- **Where:** a pure-Python package heatsetcore (profile, checks, routine math, emitter; numpy allowed, no Orca imports) beside nutcore. The Orca side adds a profile section to the docked panel, joins the slice gate and writes the blocks in the psGCodePostProcess export step.

- **Firmware:** Klipper first: EBB36 toolboard, klipper-toolchanger, the follower as \[manual_stepper hs_follower\] registered as G-code axis A, and the float as the tool's probe. RepRapFirmware later, as macro files with the same command names.

- **Changed from the earlier plan:** tool constants move from firmware into the slice-time profile, and the routine is written out step by step instead of hiding inside one INSERT_HEATSET call. Firmware keeps only what needs live sensor readings, plus hard limits the G-code can't raise.

- **Not now:** a Klipper Python extra (heatset.py) for bounded probing and a one-move push; more than one insert size per tool; plates after the first; refills mid-print.

- **If the nut plugin isn't built yet:** do its milestone 0 (the Orca API probe) and the shared plugin skeleton from docs/SPEC.md first.

Background: the [software and integration plan](https://claude.ai/artifact/Bk6KmnwXEjG2yaLHHiYpEt) and the [nut plugin build brief](https://claude.ai/artifact/X7YaFwZtnkSDpdWhpqLLAU). Export them as Markdown too if Claude Code needs them.

## Conventions

After the probe, every height is measured from the surface the pad probe finds, not from the model's z_top, so shrink and bed error drop out.

- **Units:** mm, s and °C in the profile. Speeds are mm/s, written to G-code as F in mm/min.

- **Tool point:** the centre of the tube mouth. The toolchanger's tool offsets make G-code X, Y and Z refer to the mouth, as they would to a nozzle.

- **Hole point:** (x, y) is the hole axis in bed coordinates, as the nut plugin defines placement points. z_top is the surface the insert ends flush with, snapped to the top of the layer that prints it.

- **A axis:** the follower. +A pushes the stack toward the mouth, 1 mm of A per 1 mm of stack travel; set dir_pin to match.

- **Pad offset:** (pad_dx, pad_dy) = pad centre minus mouth centre, in printer axes. To put the pad over (x, y), command X = x - pad_dx, Y = y - pad_dy.

- **Pad drop:** the pad face sits p below the mouth.

- **Probe trip:** z_trip is the G-code Z when the float trips. The surface under the pad is s = z_trip + delta - p, where delta is the travel from first contact to the trip.

- **Klipper frame trap:** PROBE leaves the tool at the trip point, so read printer.gcode_move.gcode_position.z in a macro that runs after it. Don't use printer.probe.last_z_result for moves; with tool offsets active it may not be in the G-code frame.

Symbols used below: Li insert length, e rest recess, p pad drop, h mouth gap, g proud after the hot stage, L unsheath, r retract, delta trip overtravel, s probed surface.

## Slice-time variables

The tool profile lives in the plugin settings (get_config / save_config), is edited in the docked panel, and is copied into the G-code header as comments. Keep one named profile per physical tool. Values marked TBD must be measured before normal export; the number in brackets is the placeholder.

**Measured on the prototype**

| Variable                | Unit | Default         | Meaning and how to get it                                                                                                                                                        |
|-------------------------|------|-----------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| insert_key              | –    | M3x5.7          | Insert this tool carries; must match the HSI\_\<key\> bodies. One size per tool.                                                                                                 |
| insert_length (Li)      | mm   | 5.7             | Insert length and stack pitch. M3 short: 3.0.                                                                                                                                    |
| insert_od               | mm   | 4.6             | Across the knurls.                                                                                                                                                               |
| rest_recess (e)         | mm   | TBD (0.0)       | How far the bottom insert's lower end sits above the mouth on the catch. Depth gauge from the mouth face.                                                                        |
| pad_dx, pad_dy          | mm   | TBD (20.0, 0.0) | Pad centre minus mouth centre. Ink the mouth, touch it to tape on the bed at X1, Y1, then jog the pad's centre mark over the ring at X2, Y2: pad_dx = X1 - X2, pad_dy = Y1 - Y2. |
| pad_drop (p)            | mm   | TBD (0.4)       | Pad face below the mouth. Cold, probe a flat plate with the pad (Z1), then with the mouth (Z2): p = Z1 - Z2.                                                                     |
| pad_d                   | mm   | 10.0            | Pad face diameter, for keep-out checks.                                                                                                                                          |
| tube_od                 | mm   | 5.5             | Tube tip diameter, for keep-out checks.                                                                                                                                          |
| block_r                 | mm   | TBD (12.0)      | Radius around the mouth that covers the heater block and sock.                                                                                                                   |
| block_clearance         | mm   | TBD (2.5)       | Height of the block or sock underside above the mouth.                                                                                                                           |
| trip_overtravel (delta) | mm   | TBD (0.0)       | Travel from first contact to the trip. Jog the pad down onto paper until it drags (Zc), then probe (Zt): delta = Zc - Zt.                                                        |
| float_travel            | mm   | TBD (1.0)       | Float lift left after the trip before a hard stop.                                                                                                                               |
| trip_force              | g    | TBD (650)       | Trip force on a kitchen scale; used only for the part-stability warning.                                                                                                         |

**Process, tuned on test coupons**

| Variable             | Unit | Default                        | Meaning                                                                                                               |
|----------------------|------|--------------------------------|-----------------------------------------------------------------------------------------------------------------------|
| proud_after_hot (g)  | mm   | 1.1                            | How proud the hot stage leaves the insert. Lower toward 0.6 (about 10% of Li) if the cold press stalls.               |
| mouth_gap (h)        | mm   | 0.8                            | Mouth height above the surface during the hot push. Keep it high enough that displaced plastic can't reach the mouth. |
| follower_retract (r) | mm   | 0.3                            | Follower back-off after each insert, taken up at the next push.                                                       |
| insert_temp          | °C   | PLA 225, PETG 245, ABS/ASA 265 | By filament type from the G-code config; a profile value overrides. About print temperature + 10-20 °C.               |
| temp_window          | °C   | 5                              | Allowed difference from insert_temp before a push.                                                                    |
| resist_wait          | s    | 2.0                            | Wait after the float trips during the push, so the plastic can soften.                                                |
| resist_retries       | –    | 3                              | Waits allowed per insert before aborting.                                                                             |
| press_dwell          | s    | 3.0                            | Hold after the press trips (2-5 s).                                                                                   |
| flush_tol            | mm   | 0.10                           | Allowed press trip height above the probe trip.                                                                       |
| press_guard          | mm   | 0.30                           | A press trip further than this below the probe trip counts as overpressed.                                            |
| surface_tol          | mm   | 0.50                           | Allowed difference between the probed surface and z_top.                                                              |

**Motion**

| Variable        | Unit | Default | Meaning                                                              |
|-----------------|------|---------|----------------------------------------------------------------------|
| push_step       | mm   | 0.25    | Follower travel between float checks.                                |
| push_speed      | mm/s | 0.5     | Follower speed in the hot push.                                      |
| unsheath_speed  | mm/s | 1.0     | Z and A speed in the unsheath.                                       |
| retract_speed   | mm/s | 2.0     | Follower back-off speed.                                             |
| probe_start     | mm   | 2.0     | Pad face height above z_top where probing starts.                    |
| probe_speed     | mm/s | 2.0     | Pad probe speed.                                                     |
| press_speed     | mm/s | 1.0     | Cold press speed.                                                    |
| travel_lift     | mm   | 1.5     | Lift above the placed insert before the pad moves over it.           |
| local_clear     | mm   | 3.0     | Mouth height above the surface for short moves near a hole.          |
| safe_z_clear    | mm   | 5.0     | Clearance above the tallest printed point for moves between inserts. |
| xy_travel_speed | mm/s | 150     | Moves between inserts.                                               |
| xy_local_speed  | mm/s | 30      | Short moves near a hole.                                             |
| z_travel_speed  | mm/s | 10      | Z moves between inserts.                                             |
| z_local_speed   | mm/s | 5       | Z moves near a hole.                                                 |

**Behaviour and checks**

| Variable               | Values                    | Default      | Meaning                                                                                    |
|------------------------|---------------------------|--------------|--------------------------------------------------------------------------------------------|
| tool                   | T number                  | TBD (3)      | The heat-set tool's index in the toolchanger.                                              |
| firmware               | klipper, rrf              | klipper      | Emitter flavour; rrf comes later.                                                          |
| timing                 | end_of_print, after_layer | end_of_print | after_layer runs a block right after the layer that prints z_top.                          |
| preheat_lead           | s                         | 120          | HEATSET_PREHEAT goes this long before each block, from Orca's time estimates.              |
| preheat_layers         | layers                    | 2            | Fallback lead when no time estimates are found.                                            |
| on_proud               | warn, pause               | warn         | Action when the press check fails.                                                         |
| mode                   | normal, rehearse          | normal       | Rehearse: no heat, no follower moves, no contact; routine heights raised by rehearse_lift. |
| rehearse_lift          | mm                        | 10.0         | Extra height for every routine move in rehearse mode.                                      |
| hole_d_min, hole_d_max | mm                        | 3.90, 4.20   | Accepted hole diameters for M3 (nominal 4.0).                                              |
| hole_extra_depth       | mm                        | 1.0          | Blind holes at least this much deeper than Li.                                             |
| min_wall               | mm                        | 1.6          | Minimum wall around the hole.                                                              |

**Derived, never typed (print them in the header)**

- L = g - h: the unsheath lift and follower feed.

- push = h + e + Li - g: follower travel in the hot push.

- push + L = Li + e: one insert per cycle; assert it.

- ticks = ceil(push / push_step) + resist_retries + 1.

- During the push the pad face sits h - p above the surface; during the press the mouth sits p above it.

**Validation: export refuses, naming the rule**

1.  0 \< p \< h \<= g \< Li and e \>= 0.

2.  travel_lift \>= p + 0.3, so the pad clears the insert top as it moves over.

3.  local_clear \>= g + 1.0 and local_clear - p \>= 1.0.

4.  push_step \<= float_travel / 2.

5.  Every TBD set, unless mode = rehearse.

6.  insert_temp at or below the firmware limit (290 °C).

7.  Per insert: hole diameter in range, depth at least Li + hole_extra_depth, wall at least min_wall, surface facing +Z within 0.5°, and no plastic in the hole (reuse the nut gate).

8.  Keep-out per insert, heights above z_top. During the push: nothing within block_r of the hole above h + block_clearance, and nothing within pad_d / 2 of (x + pad_dx, y + pad_dy) above h - p. During the press: nothing within block_r of (x - pad_dx, y - pad_dy) above p + block_clearance, and nothing within tube_od / 2 of it above p. In practice each hole needs about one pad offset of clear surface on both sides along the pad axis; report which side is blocked.

9.  Inserts in the print at most the magazine capacity, about 12-13 with the 100 mm screw. More needs a refill stop, which is out of scope.

**Warning, export continues:** a part that may tip or slide under trip_force, judged by its bed contact area against its height.

## The insertion routine

Every insert runs the same eleven steps. Bracketed names are the firmware commands the G-code calls; heights after step 4 are above s.

1.  **Start** \[HEATSET_INSERT_START\]: skip the insert if its object is excluded. Check stock of at least 1, the throat within temp_window, and the float reading open.

2.  **Travel:** mouth to z_safe, then XY to (x - pad_dx, y - pad_dy), putting the pad over the hole.

3.  **Approach:** mouth to z_top + probe_start + p, so the pad face is probe_start above z_top.

4.  **Probe** \[HEATSET_PROBE\]: lower until the float trips. Store z_trip1 and s = z_trip1 + delta - p; refuse if abs(s - z_top) \> surface_tol.

5.  **Line up:** mouth to local_clear, XY to (x, y), then mouth to h.

6.  **Hot push** \[\_HS_PUSH_START, \_HS_PUSH_TICK, \_HS_PUSH_END\]: take up any pending retract, then feed A by push in steps of push_step, checking the float after each. A trip means the insert resists: wait resist_wait and check again, up to resist_retries times, then abort. The insert ends g proud, its top L inside the tube.

7.  **Unsheath** \[HEATSET_UNSHEATH\]: one move, Z up L and A forward L, skipped when L = 0. The stack stays still against the part while the tube slides off, and the catch moves onto the next insert.

8.  **Retract** \[HEATSET_RETRACT\]: A back r; firmware records it for the next push.

9.  **Lift and swap:** mouth to g + travel_lift, then XY to (x - pad_dx, y - pad_dy), the pad over the insert.

10. **Cold press** \[HEATSET_PRESS\]: lower until the float trips (z_trip2) and hold press_dwell. proud = z_trip2 - z_trip1; the pad drop and delta cancel. Over flush_tol runs on_proud; under -press_guard logs an overpress warning.

11. **Finish** \[HEATSET_INSERT_DONE\]: mouth to local_clear, count minus 1, save it, and log the index, key, XY, s - z_top, waits and proud.

## Emitted G-code

The emitter writes a header after the start G-code, preheat lines, and one block per insertion time; nothing else in the file changes.

**Placement**

- **Header:** right after the slicer's start G-code. Every profile value and derived value as a comment, then HEATSET_CONFIG and HEATSET_REQUIRE.

- **Preheat:** HEATSET_PREHEAT goes preheat_lead seconds before each block, from Orca's per-layer time estimates (to confirm where the export step can read them); otherwise preheat_layers layer changes before.

- **Blocks:** end_of_print goes just before the end G-code. after_layer goes after the layer whose top is z_top, before the next ;LAYER_CHANGE; inserts on the same layer share a block.

- **Order** within a block: nearest neighbour, starting with the insert closest to the last toolhead position.

- **z_safe** for a block: the tallest printed Z so far plus safe_z_clear.

- **Numbers:** X, Y, Z and A with 3 decimals; F as a whole number in mm/min; firmware speeds in mm/s with 1 decimal.

**Klipper templates**

Header:

```gcode
; HEATSET profile "{profile_name}" heatsetcore {version}
; {variable} = {value}   (one line per profile value, then the derived values)
HEATSET_CONFIG KEY={insert_key} TOOL={tool} PAD_DROP={p} TRIP_OVERTRAVEL={delta} SURFACE_TOL={surface_tol} TEMP_WINDOW={temp_window} ON_PROUD={on_proud} MODE={mode} REHEARSE_LIFT={rehearse_lift}
HEATSET_REQUIRE KEY={insert_key} COUNT={total_inserts} TEMP={temp}
```

Block, with the insert part repeated for each insert:

```gcode
; HEATSET block {b}: {timing}, inserts={n}, key {insert_key}
HEATSET_BEGIN KEY={insert_key} TEMP={temp} Z_SAFE={z_safe} COUNT={n}
; insert {i}/{n} {object} X{x} Y{y} Ztop{z_top}
HEATSET_INSERT_START INDEX={i} OBJECT={object} X={x} Y={y} Z_TOP={z_top}
G90
G0 Z{z_safe} F{z_travel_speed*60}
G0 X{x-pad_dx} Y{y-pad_dy} F{xy_travel_speed*60}
G0 Z{z_top+probe_start+p} F{z_local_speed*60}
HEATSET_PROBE SPEED={probe_speed}
HEATSET_Z HEIGHT={local_clear} SPEED={z_local_speed}
G0 X{x} Y{y} F{xy_local_speed*60}
HEATSET_Z HEIGHT={h} SPEED={z_local_speed}
_HS_PUSH_START TOTAL={push} STEP={push_step} SPEED={push_speed} WAIT={resist_wait} MAXWAITS={resist_retries}
_HS_PUSH_TICK            ; this line {ticks} times
_HS_PUSH_END
HEATSET_UNSHEATH DIST={L} SPEED={unsheath_speed}   ; only when L > 0
HEATSET_RETRACT DIST={r} SPEED={retract_speed}
HEATSET_Z HEIGHT={g+travel_lift} SPEED={z_local_speed}
G0 X{x-pad_dx} Y{y-pad_dy} F{xy_local_speed*60}
HEATSET_PRESS SPEED={press_speed} DWELL={press_dwell} TOL={flush_tol} GUARD={press_guard}
HEATSET_Z HEIGHT={local_clear} SPEED={z_local_speed}
HEATSET_INSERT_DONE
HEATSET_END
```

**Worked example (golden test)**

Defaults, with the placeholder for every TBD; PETG at 245 °C; tool 3; one insert on object bracket_1 at X 120, Y 80, z_top 12.4; end_of_print; tallest printed point 12.4. Derived: L 0.3, push 5.4, ticks 26, z_safe 17.4.

```gcode
; HEATSET block 1: end_of_print, inserts=1, key M3x5.7
HEATSET_BEGIN KEY=M3x5.7 TEMP=245 Z_SAFE=17.400 COUNT=1
; insert 1/1 bracket_1 X120.000 Y80.000 Ztop12.400
HEATSET_INSERT_START INDEX=1 OBJECT=bracket_1 X=120.000 Y=80.000 Z_TOP=12.400
G90
G0 Z17.400 F600
G0 X100.000 Y80.000 F9000
G0 Z14.800 F300
HEATSET_PROBE SPEED=2.0
HEATSET_Z HEIGHT=3.000 SPEED=5.0
G0 X120.000 Y80.000 F1800
HEATSET_Z HEIGHT=0.800 SPEED=5.0
_HS_PUSH_START TOTAL=5.400 STEP=0.250 SPEED=0.5 WAIT=2.0 MAXWAITS=3
_HS_PUSH_TICK
_HS_PUSH_END
HEATSET_UNSHEATH DIST=0.300 SPEED=1.0
HEATSET_RETRACT DIST=0.300 SPEED=2.0
HEATSET_Z HEIGHT=2.600 SPEED=5.0
G0 X100.000 Y80.000 F1800
HEATSET_PRESS SPEED=1.0 DWELL=3.0 TOL=0.100 GUARD=0.300
HEATSET_Z HEIGHT=3.000 SPEED=5.0
HEATSET_INSERT_DONE
HEATSET_END
```

The golden file has \_HS_PUSH_TICK on 26 lines in a row; it is shown once here.

Heights above s in the example, for the routine-math tests:

| After step           | Mouth (mm) | Pad face (mm) | Insert top (mm)      |
|----------------------|------------|---------------|----------------------|
| 5 Line up            | 0.8        | 0.4           | 6.5, inside the tube |
| 6 Hot push           | 0.8        | 0.4           | 1.1                  |
| 7 Unsheath           | 1.1        | 0.7           | 1.1                  |
| 9 Lift and swap      | 2.6        | 2.2           | 1.1                  |
| 10 Press trip, flush | 0.4        | 0.0           | 0.0                  |

## Firmware commands (Klipper)

The G-code only calls these commands. They go in firmware/klipper/heatset_macros.cfg, beside the heatset.cfg from the plan (\[heater_generic hs_throat\], \[manual_stepper hs_follower\], the tool probe, \[save_variables\], \[neopixel\], \[gcode_button\]). Every A move goes through a command, so firmware can apply limits and rehearse mode; every command does nothing while the insert's skip flag is set.

| Command              | Parameters                                                                            | What it does                                                                                                                         |
|----------------------|---------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------|
| HEATSET_CONFIG       | KEY TOOL PAD_DROP TRIP_OVERTRAVEL SURFACE_TOL TEMP_WINDOW ON_PROUD MODE REHEARSE_LIFT | Checks the values against \_HS_LIMITS and stores them in \_HS_STATE for this print.                                                  |
| HEATSET_REQUIRE      | KEY COUNT TEMP                                                                        | Before the first layer: right key loaded, stock at least COUNT, TEMP within limits; otherwise pause with a refill prompt.            |
| HEATSET_PREHEAT      | TEMP                                                                                  | Sets the throat target without waiting.                                                                                              |
| HEATSET_BEGIN        | KEY TEMP Z_SAFE COUNT                                                                 | Saves G-code state and the current tool, lifts to Z_SAFE, selects the heat-set tool, waits for TEMP within the window, checks stock. |
| HEATSET_INSERT_START | INDEX OBJECT X Y Z_TOP                                                                | Resets the insert's state; sets skip if OBJECT is excluded; checks stock, temperature and that QUERY_PROBE reads open.               |
| HEATSET_PROBE        | SPEED                                                                                 | Runs PROBE SAMPLES=1 PROBE_SPEED=SPEED, then a follow-up macro stores z_trip1 and s and checks surface_tol.                          |
| HEATSET_Z            | HEIGHT SPEED                                                                          | Moves the mouth to s + HEIGHT.                                                                                                       |
| \_HS_PUSH_START      | TOTAL STEP SPEED WAIT MAXWAITS                                                        | Takes up any pending retract, zeroes progress and waits, runs QUERY_PROBE.                                                           |
| \_HS_PUSH_TICK       | none                                                                                  | One step of the push, below.                                                                                                         |
| \_HS_PUSH_END        | none                                                                                  | Aborts the insert if the push didn't finish.                                                                                         |
| HEATSET_UNSHEATH     | DIST SPEED                                                                            | One move: Z up DIST and A forward DIST, both at SPEED.                                                                               |
| HEATSET_RETRACT      | DIST SPEED                                                                            | Moves A back DIST and records it as pending.                                                                                         |
| HEATSET_PRESS        | SPEED DWELL TOL GUARD                                                                 | Needs QUERY_PROBE open; PROBE, G4 DWELL, then a follow-up macro computes proud and acts.                                             |
| HEATSET_INSERT_DONE  | none                                                                                  | Count minus 1, SAVE_VARIABLE, LED, one log line; clears skip.                                                                        |
| HEATSET_END          | none                                                                                  | Lifts to Z_SAFE, returns to the saved tool, restores state.                                                                          |

HEATSET_HOME, HEATSET_LAND, HEATSET_REFILL and HEATSET_CALIBRATE_PAD stay as in the plan; print G-code never calls them.

Push tick, run once per emitted line:

```text
_HS_PUSH_TICK:
  if skip or done: stop
  if printer.probe.last_query is triggered:      # float tripped: insert resists
      waits += 1
      if waits > MAXWAITS: abort("insert resists")
      else: G4 P{WAIT*1000}; QUERY_PROBE
  elif progress < TOTAL:
      d = min(STEP, TOTAL - progress)
      G91; G1 A{d} F{SPEED*60}; G90; M400; QUERY_PROBE
      progress += d
  else:
      done = true                                 # at target, float open
```

Klipper constraints to design around:

- **Render before run:** Klipper renders a macro's whole template before any of its lines run, so a macro can't read a result it causes. Do the action, then call a follow-up macro, which renders when it is called.

- **No loops on sensor results:** macros can't call themselves, directly or through another macro. That's why the emitter unrolls the push into ticks lines.

- **PROBE has no travel limit:** if the float never trips, it runs to the Z axis minimum. Phase 1 guards: QUERY_PROBE must read open first, probe speeds stay slow, and the wiring reads triggered when unplugged. The Python extra adds a bounded probe later.

- **Axis A:** hs_follower is registered as A for prints and unregistered for HEATSET_HOME and HEATSET_LAND. In HEATSET_UNSHEATH, check how the installed Klipper applies F to a move that includes A.

- **State:** one \[gcode_macro \_HS_STATE\] holds the config, z_trip1, s, pending retract, push progress, waits, flags and count; the count persists with SAVE_VARIABLE.

- **Abort:** set skip, stay in place (no parking), set the throat to standby, and pause with the base pause command and a message naming the insert and the reason. Recovery is manual in v1.

**RepRapFirmware, later:** one macro file per command under macros/heatset/, called as M98 P"heatset/\<name\>.g", with value letters that avoid G, M, N, T and P. G38.2 K\<probe\> gives a bounded probe, and G38.3 can push A until the float trips, so the push needn't be unrolled.

## Failures and safety limits

Firmware decides what happens on a failure. The G-code only passes thresholds, and firmware limits cap anything it passes.

| Failure                                             | Caught by                    | Action                                                                 |
|-----------------------------------------------------|------------------------------|------------------------------------------------------------------------|
| Float reads tripped before a probe or press         | QUERY_PROBE                  | Abort: stuck float or debris.                                          |
| Probed surface off by more than surface_tol         | HEATSET_PROBE                | Abort before heat touches the part: part moved, warped or wrong layer. |
| Float never trips                                   | Nothing in phase 1           | Guards in the Klipper section; bounded probe in the Python extra.      |
| Insert still resists after resist_retries waits     | Push ticks                   | Abort in place.                                                        |
| Insert proud by more than flush_tol after the press | HEATSET_PRESS                | on_proud: warn (log, LED amber) or pause.                              |
| Press trips more than press_guard below the probe   | HEATSET_PRESS                | Warn: plastic too soft or delta wrong.                                 |
| Stock short                                         | REQUIRE, BEGIN, INSERT_START | Pause with a refill prompt; REQUIRE catches it before printing starts. |
| Throat outside temp_window                          | BEGIN, INSERT_START          | Wait up to 60 s, then pause.                                           |
| Object excluded                                     | HEATSET_INSERT_START         | Skip the insert and log it.                                            |

Hard limits live in \[gcode_macro \_HS_LIMITS\] in the printer config, never in G-code:

- Throat at most 290 °C, matching max_temp in the plan.

- A at most 0.5 mm per tick, 8 mm per push and 2 mm per unsheath.

- Dwells and waits at most 10 s; probe and press speeds at most 5 mm/s.

- Routine commands refuse to run outside a HEATSET_BEGIN to HEATSET_END pair; CONFIG, REQUIRE and PREHEAT are the exceptions.

**Rehearse mode**, set by MODE=rehearse in the header: the heater stays off, A never moves, and nothing touches the part. HEATSET_PROBE sets s = Z_TOP + rehearse_lift without probing, HEATSET_PRESS lowers the pad to s and dwells, and the count doesn't change. The routine lines are the same in both modes, so a rehearse run tests the real G-code.

## Tests and acceptance

Work in this order; each milestone ends with its tests passing.

1.  **Profile:** schema with defaults and TBD markers, saved and loaded through the plugin settings, and a test that breaks each validation rule.

2.  **Routine math:** derived values, push + L = Li + e, the tick count, and the heights table from the worked example.

3.  **Klipper emitter:** header, block and insert templates; the worked example as a golden file, byte for byte; rehearse output differing only in MODE.

4.  **Placement:** header after the start G-code, the HEATSET_REQUIRE count, preheat lead and fallback, end_of_print and after_layer blocks, nearest-neighbour order. Test on a real Orca G-code file (the nut plugin's milestone 0 sample).

5.  **Checks:** hole size, depth and wall, facing +Z, no plastic in the hole, and the keep-out footprints. Slice gate messages name the insert and the rule.

6.  **Klipper macros:** heatset_macros.cfg implementing every command, render-checked in Klipper's batch mode where it runs, otherwise on the printer in rehearse mode.

7.  **Printer bring-up (manual):** a rehearse run over a printed coupon; measure and fill every TBD; then single inserts into flat coupons, tuning g and h.

Done means:

- Export refuses with a readable message for any failed rule, or any TBD left in normal mode.

- Every number in the emitted G-code traces to the profile, the model or a formula here; templates hold no other numbers.

- The worked-example golden file matches.

- On the printer, a rehearse run finishes without errors, and a coupon insert ends within flush_tol with its log line.
