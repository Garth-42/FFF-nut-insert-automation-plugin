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

## Bring-up, rehearse mode first

In the plugin, set the heat-set profile's firmware to Klipper and its mode to Rehearse, and
export a coupon with one insert. In rehearse mode the throat stays off, the follower never
moves, nothing probes (the surface is taken as z_top + rehearse_lift) and the count does not
change: every move of the routine runs rehearse_lift above the part, apart from the approach,
which stops with the pad probe_start above it.

1. Print it and watch each step. The console says `insert 1 rehearsed`.
2. Check, and note the results in `docs/manual-test.md`:
   - `QUERY_PROBE` reads triggered with the float pressed and unplugged, open otherwise;
   - `PROBE` stops when the float trips and leaves the tool there;
   - after `HEATSET_CONFIG` in normal mode, `G91`, `G1 A1 F60`, `G90` moves the follower 1 mm;
   - the unsheath (`G1 Z.. A.. F..`) moves Z and A together at the same speed;
   - excluding an object in the web interface skips its inserts;
   - your pause command does not park the toolhead.
3. Measure every TBD in the Machine settings tab, then go to normal mode with one insert in a
   flat coupon.
