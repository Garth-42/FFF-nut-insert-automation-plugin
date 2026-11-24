; heatset/retract.g: HEATSET_RETRACT, step 8: back the follower off.
;
;   M98 P"heatset/retract.g" D<follower_retract> V<retract_speed>
;
; Moves axis A back D and records it, so the next push takes it up first. The record is
; kept across restarts (heatset/save.g). Rehearse mode never moves A.

if !global.hs_in_block
  abort "heatset/retract.g: outside a heatset/begin.g to heatset/end.g block"
if global.hs_skip || global.hs_mode != "normal"
  M99
if param.D < 0 || param.D > global.hs_max_unsheath
  M98 P"heatset/fail.g" S{"a retract of " ^ param.D ^ " mm is over the limit of " ^ global.hs_max_unsheath ^ " mm"}
  M99
if param.D == 0
  M99

M400
if move.axes[global.hs_a].userPosition - param.D < move.axes[global.hs_a].min
  M98 P"heatset/fail.g" S"the follower would pass its start (axis A minimum)"
  M99
G91
G1 A{-param.D} F{param.V * 60}
G90
set global.hs_pending_retract = global.hs_pending_retract + param.D
M98 P"heatset/save.g"
