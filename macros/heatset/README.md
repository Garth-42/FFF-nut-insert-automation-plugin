# Heat-set macros for RepRapFirmware

The heat-set G-code the plugin writes calls these macros, one `M98 P"heatset/<name>.g"`
line per command of `docs/HEATSET_GCODE_SPEC.md`. They need RepRapFirmware 3.6 or later
(standalone). They have not run on a printer yet: bring them up in rehearse mode first
(below), with a hand near the emergency stop.

## Install

1. Upload every `.g` file in this folder to `/sys/heatset/` on the printer (Duet Web
   Control, System, make the folder `heatset`). `M98` looks for `heatset/<name>.g` under
   `/sys`. Do not put them in `/sys/` itself: `config.g` here is the heat-set header's
   macro, not the printer's.
2. In `/sys/config.g`, define the heat-set tool, the follower and the float, then add the
   last line:
   - the tool (`M563`) with the throat heater (`M950`, `M307`, `M143` at or below 290 C),
     and its offsets (`G10`) so that X, Y and Z are the centre of the tube mouth;
   - the follower as axis A, **linear** (`M584 A... R0`), with `M92`, `M203`, `M208` limits
     covering its travel, and a way to home it;
   - the float as a probe (`M558 K<n> P<type> C"<pin>"`, threshold with `G31 K<n> P500`),
     reading triggered when unplugged;
   - `M98 P"heatset/init.g"`.
3. Edit `limits.g`: the float's probe number (`hs_probe`) and anything you want lower.
4. Restart. The console says `heatset: ready`.
5. Load the magazine and tell the macros: `M98 P"heatset/refill.g" K"M3x5.7" C12`.

The plugin's Machine settings tab must match: the tool number, and firmware
RepRapFirmware.

## What each file does

Called by the print G-code, in this order:

| File | Spec command | Does |
| --- | --- | --- |
| `config.g` | HEATSET_CONFIG | In the header: checks the tool, axis A, the float and the values; keeps them for the print. Ends the print if anything is wrong, before anything is printed |
| `require.g` | HEATSET_REQUIRE | In the header: the key, the temperature limit, the follower homed, enough inserts |
| `preheat.g` | HEATSET_PREHEAT | Heats the throat ahead of a block without selecting the tool |
| `begin.g` | HEATSET_BEGIN | Lifts to the safe height, selects the heat-set tool, waits for the throat, checks the magazine |
| `insert_start.g` | HEATSET_INSERT_START | Skips the insert if its object is cancelled; checks position, magazine, temperature, the float open |
| `probe.g` | HEATSET_PROBE | Lowers until the float trips and takes the surface from it; refuses a surface off by more than surface_tol |
| `z.g` | HEATSET_Z | Mouth to a height above the probed surface |
| `push.g` | the hot push | Feeds the follower until the push is done; waits when the insert resists, at most resist_retries times |
| `unsheath.g` | HEATSET_UNSHEATH | Mouth up and follower forward together, so the tube slides off the insert |
| `retract.g` | HEATSET_RETRACT | Backs the follower off; the next push takes it up |
| `press.g` | HEATSET_PRESS | Presses with the pad until the float trips, dwells, and checks how proud the insert is |
| `insert_done.g` | HEATSET_INSERT_DONE | Counts the insert out of the magazine and logs it |
| `end.g` | HEATSET_END | Lifts to the safe height and gives the print back to the print tool |

Used by the others, or by you:

| File | Does |
| --- | --- |
| `init.g` | Declares the globals, runs `limits.g`, finds axis A, reads `count.g`. From `config.g` |
| `limits.g` | Hard limits and wiring: 290 C, 8 mm per push, 2 mm per unsheath or retract, 10 s waits, 5 mm/s probe and press |
| `heat.g` | Waits for the throat, up to `hs_temp_settle` seconds |
| `stock.g` | Asks for a refill while the magazine is short |
| `fail.g` | Stops an insert or a block and asks: go on without it, or stop the print |
| `stop.g` | Ends the print: throat and print tool heaters off, then `abort` |
| `save.g` | Writes `count.g`: inserts left, their key, the pending follower retract |
| `refill.g` | You run it after loading the magazine |

Bring-up checks, which you run from the console (below):

| File | Does |
| --- | --- |
| `check_float.g` | Reads the float free, then watches 15 s for you to push it up. Nothing moves |
| `check_follower.g` | Moves axis A forward D mm and back (default 1 mm), after asking |
| `check_probe.g` | Lowers at most D mm until the float trips, reports the height, goes back up, after asking |

`count.g` and `log.csv` are written on the printer. `log.csv` gets one line per insert:
index, key, X, Y, surface minus z_top, waits, proud, and done, rehearsed or skipped.

## When something fails

The spec stops an insert in place, throat to standby, with a message. In RepRapFirmware,
`abort` would end the print, and after a pause and resume the print's own moves would
run on with the tool where it stopped, perhaps touching the part. So `fail.g` stays in
place and asks:

- **Go on**: the rest of that insert (or block) does nothing, the tool lifts straight up
  to the block's safe height, and the throat heats again for the next insert.
- **Stop the print**: the throat and the print tool's heater are turned off and the
  print ends with `abort`. Check the bed and the part yourself.

A stopped insert is not counted out of the magazine, since it may have gone into the
part or stayed in the tube: look, and set the count with `refill.g` before going on.
An insert that stays proud by more than flush_tol warns, or with on_proud `pause` asks
the same question. The magazine running short asks for a refill: answer Refilled and
type how many are loaded.

## Bring-up, one step at a time

Each step comes before the plugin's G-code touches anything. Keep a hand near the
emergency stop. Note what you see in `docs/manual-test.md`, check H.

1. **Install and restart** as above. The console says `heatset: ready`.
2. **The float.** `M98 P"heatset/check_float.g"`: it must read open, then trip when you
   push it up within 15 seconds. Unplug the float and run it again: it must read tripped.
3. **The follower.** Home axis A, empty the magazine, then
   `M98 P"heatset/check_follower.g" D1 V1`: the stack side moves 1 mm toward the mouth and
   back.
4. **The probe.** Select the heat-set tool (`T3`), put the pad a few mm over a flat plate,
   and run `M98 P"heatset/check_probe.g" D5 V1` a few times: the trip height should repeat
   within a few hundredths of a millimetre.
5. **The air test.** On your computer, with the settings JSON from the Nut panel's Export
   button saved as `nut_settings.json`:

   ```bash
   uv run python -m heatsetcore.bringup --x 150 --y 150 --z 40 \
       --settings nut_settings.json --out air_test.gcode
   ```

   It is one insert's routine in rehearse mode, its surface 40 mm over the bed. Upload it,
   run `M37 P"air_test.gcode"` first (simulation: the macros run, nothing moves, errors
   show in the console), then print it with the bed clear: the tool change and every move
   of the routine, no heat, no follower move, `rehearsed` in `/sys/heatset/log.csv`. Pick X
   and Y so that X - pad_dx is on the bed too.
6. **A coupon, rehearse mode.** Slice `models/heatset_bringup_coupon.3mf` with the profile
   in Rehearse mode (`models/README.md`) and print it: the routine runs above the coupon's
   hole, the pad never closer than probe_start.
7. **Measure every TBD** in the Machine settings tab, as the spec's table says, then normal
   mode with one insert in the bring-up coupon.

`tests/test_rrf_macros.py` already runs these macros on the plugin's G-code in a stand-in
for RepRapFirmware (`tests/rrf_sim.py`): a normal print, rehearse mode and every failure
path. What only the printer can show, so check it along the way:

- `G38.3 K<n> A... F...` stops on axis A when the float trips, as it does on Z;
- the unsheath moves Z and A at the same speed (`F` is V × 60 × √2 for a linear A);
- an object cancelled in Duet Web Control skips its inserts (`insert_start.g` matches the
  object name the G-code passes in `O`);
- the dialogs show in Duet Web Control or on the PanelDue, and the print waits for them;
- "Stop the print" ends the print and turns the heaters named above off, and whether RRF
  also runs `cancel.g` then.
