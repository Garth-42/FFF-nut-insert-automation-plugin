# Test models for heat-set inserts

Closed meshes, made by `tests/models3mf.py` (run `uv run python tests/models3mf.py` after
changing it). Each coupon is one object of two parts: the block (`Coupon`) and the insert
body in its hole (`HEATSET_M3x5.7`, a 4.6 x 5.7 mm cylinder flush with the top).
`tests/test_models.py` checks the files are closed and gives each coupon the findings below.

## Loading them in OrcaSlicer

1. Import the file. If Orca asks whether to load it as a single object with multiple parts,
   answer **No**: each coupon is its own object.
2. Check each object holds two parts. If Orca named them differently, rename the insert body
   to `HEATSET_M3x5.7` (right-click, Rename), or `HEATSET_M4x8` on coupon 7. If a coupon
   arrives as one merged part, the body cannot be told apart from the block: note it in
   `docs/manual-test.md`, check F, and the files can be written in Orca's own project
   format instead.
3. Set every insert body to **Modifier** (right-click, Change type, Modifier). One left as a
   part shows `E_NOT_MODIFIER`, which is worth seeing once too.
4. Press Check nuts.

With the default heat-set profile every insert also shows `E_PROFILE` (rule 5: values still
to measure) until you measure them or switch the profile to Rehearse.

## heatset_check_coupons.3mf: check F

| Coupon | What is wrong | Finding |
| --- | --- | --- |
| 1 good | Nothing | none |
| 2 wide hole | The hole is 4.3 mm across, 3.9–4.2 allowed | `E_HOLE_DIAMETER` |
| 3 shallow hole | The hole is 6.0 mm deep, 6.7 needed | `E_DEPTH` |
| 4 thin wall | 1.5 mm of wall, 1.6 needed | `E_WALL` |
| 5 through hole | Nothing: no depth rule for a through hole | none |
| 6 off centre | The body sits 0.2 mm off the hole's axis | `N_OFF_CENTRE` (a note; the hole's axis is used) |
| 7 unknown insert | The body is named for an M4x8 insert, which has no profile | `E_NAME_UNKNOWN` |
| 8 tilted | The coupon is tilted 20 degrees | `W_TILTED` (fit by hand) |
| 9 body below the floor | The body reaches 0.5 mm below the hole's floor | `E_INTERFERENCE` |
| 10 small and tall | 8 x 8 mm on the bed, 30 mm tall | `W_HOLD_DOWN` |

If Orca puts coupon 8 flat on the bed, rotate it 20 degrees about X to see `W_TILTED`.

## heatset_bringup_coupon.3mf: checks G, H and I

A 30 x 30 x 8 mm coupon with one good hole, 4.0 mm across and 6.7 mm deep, for the first
rehearse runs and then the first real insert. In rehearse mode the routine runs
rehearse_lift above it and nothing touches it.
