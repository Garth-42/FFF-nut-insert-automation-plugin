; heatset/unsheath.g: HEATSET_UNSHEATH, step 7: slide the tube off the insert.
;
;   M98 P"heatset/unsheath.g" D<L> V<unsheath_speed>
;
; One move: the mouth up D and the follower forward D, both at V mm/s, so the stack stays
; still against the part while the tube slides off. Axis A must be linear (M584 ... R0):
; F covers the whole move, and both axes move D, so F is V * 60 * sqrt(2). Rehearse mode
; lifts the mouth only.

if !global.hs_in_block
  abort "heatset/unsheath.g: outside a heatset/begin.g to heatset/end.g block"
if global.hs_skip
  M99
if param.D <= 0 || param.D > global.hs_max_unsheath
  M98 P"heatset/fail.g" S{"an unsheath of " ^ param.D ^ " mm is over the limit of " ^ global.hs_max_unsheath ^ " mm"}
  M99

M400
if global.hs_mode != "normal"
  G91
  G1 Z{param.D} F{param.V * 60}
  G90
  M99
if move.axes[global.hs_a].userPosition + param.D > move.axes[global.hs_a].max
  M98 P"heatset/fail.g" S"the follower would pass its end (axis A maximum)"
  M99
G91
G1 Z{param.D} A{param.D} F{param.V * 60 * sqrt(2)}
G90
