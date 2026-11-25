# Heat-set commands for Klipper

The heat-set G-code the plugin writes for a profile with firmware **Klipper** calls the
commands in `heatset_macros.cfg`: the spec's `HEATSET_*` commands and the push ticks
(`docs/HEATSET_GCODE_SPEC.md`, "Firmware commands (Klipper)"). They have not run on a printer
yet. `tests/test_klipper_macros.py` runs them in a stand-in for Klipper
(`tests/klipper_sim.py`) on the plugin's own G-code; bring them up in rehearse mode first, as
below, with a hand near the emergency stop.

## Files

- `heatset_macros.cfg`: the commands. Replace it when it changes.
- `heatset_limits.cfg`: `_HS_LIMITS`, the hard limits and the names of your heater, follower,
  pause command and LED. Yours to edit; the G-code never changes these.
- `heatset_checks.cfg`: bring-up checks, `HEATSET_CHECK_FLOAT` and `HEATSET_CHECK_FOLLOWER`.
  Optional; nothing in a print calls them.

## What your printer config needs

These come from your heat-set tool's own config (`heatset.cfg` in the integration plan); the
names are the defaults in `heatset_limits.cfg`:

- klipper-toolchanger, with the heat-set tool given a `tool_number` (3 in the default
  profile) so that `T3` exists, and its offsets making X, Y and Z the centre of the tube mouth.
- `[heater_generic hs_throat]` for the throat, with `max_temp` at or below `max_temp` in
  `_HS_LIMITS` (290 C).
- `[manual_stepper hs_follower]` for the follower, with `position_min`/`position_max` covering
  its travel. `HEATSET_CONFIG` registers it as axis A at the start of a print
  (`MANUAL_STEPPER STEPPER=hs_follower GCODE_AXIS=A`) unless it already is. +A pushes the stack
  toward the mouth, 1 mm per mm.
- The float as the heat-set tool's probe (`[tool_probe]` and `[tool_probe_endstop]`), wired so
  that it reads triggered when unplugged.
- `[save_variables]` (the magazine count, its key and the pending follower retract are kept
  there as `hs_count`, `hs_key` and `hs_pending`), `[respond]`, `[pause_resume]` and
  `[exclude_object]`.
- Optional: a `[neopixel]` or `[led]` named in `_HS_LIMITS` for the status colours.

Then, in `printer.cfg`, after your tool config:

```ini
[include heatset_limits.cfg]
[include heatset_macros.cfg]
[include heatset_checks.cfg]
```

Load the magazine and tell the macros: `HEATSET_REFILL KEY=M3x5.7 COUNT=12`.

`HEATSET_HOME`, `HEATSET_LAND` and `HEATSET_CALIBRATE_PAD` stay with your tool's config, as
the integration plan has them. Print G-code never calls them.

## When something fails

The spec stops an insert in place, throat to standby, and pauses. Klipper cannot ask a
question mid-print, and `RESUME` moves the tool back to where the pause happened before the
print's own `G0` lines run on, which could drag the pad or a half-set insert across the part.
So a stopped insert (`_HS_ABORT`) does the rest of the spec's abort, but first lifts the tool
**straight up** to the block's safe height, then pauses with your pause command that does not
park (`PAUSE_BASE` with the Mainsail or Fluidd macros):

- **Resume** goes on without that insert: its remaining commands do nothing and its moves run
  at the safe height. Other inserts go on as normal, and the throat heats again for them.
- **Cancel** the print to stop.

A stopped insert is not counted out of the magazine: check it, and correct the count with
`HEATSET_REFILL` before resuming. A short magazine or a throat that does not reach its
temperature within `temp_settle` seconds pauses without skipping; the probe checks both again
before it moves, so resuming before fixing them stops that insert instead.

`PROBE` has no travel limit in Klipper (the spec's phase 1): the macros check that the float
reads open before every probe and press, and keep probe and press speeds under `max_speed`.

## Bring-up, one step at a time

Each step comes before the plugin's G-code touches anything. Keep a hand near the
emergency stop. Note what you see in `docs/manual-test.md`, check I.

1. **The float.** `HEATSET_CHECK_FLOAT` with the float free (open), pushed up by hand
   (TRIPPED) and unplugged (TRIPPED).
2. **The follower.** Empty the magazine, then `HEATSET_CHECK_FOLLOWER DIST=1 SPEED=1`: the
   stack side moves 1 mm toward the mouth and back.
3. **The probe.** Select the heat-set tool, put the pad a few mm over a flat plate and run
   `PROBE PROBE_SPEED=1` a few times: it must stop when the float trips. Klipper's `PROBE`
   has no travel limit, so stay ready to stop it.
4. **The air test.** On your computer, with the settings JSON from the Nut panel's Export
   button saved as `nut_settings.json`:

   ```bash
   uv run python -m heatsetcore.bringup --x 150 --y 150 --z 40 --firmware klipper \
       --settings nut_settings.json --out air_test.gcode
   ```

   One insert's routine in rehearse mode, its surface 40 mm over the bed. Print it with the
   bed clear: the tool change and every move, no heat, no follower move, `insert 1
   rehearsed` in the console. Pick X and Y so that X - pad_dx is on the bed too.
5. **A coupon, rehearse mode.** Slice `models/heatset_bringup_coupon.3mf` with the profile in
   Rehearse mode (`models/README.md`) and print it.
6. **Measure every TBD** in the Machine settings tab, then normal mode with one insert in the
   bring-up coupon.

What only the printer can show, so check it along the way: `GCODE_AXIS=A` registration and
`G1 A..` moves; the unsheath (`G1 Z.. A.. F..`) moving Z and A at the same speed; an object
excluded in the web interface skipping its inserts; your pause command not parking.
