; heatset/fail.g: stop an insert, or a whole block, and ask what to do.
;
;   M98 P"heatset/fail.g" S"<reason>"        the current insert
;   M98 P"heatset/fail.g" S"<reason>" L1     the whole block (from heatset/begin.g)
;
; The spec's abort: stay in place, throat to standby, a message naming the insert and the
; reason. RRF's abort would end the print, and after a pause and resume the print's own
; moves would run on with the tool where it stopped, perhaps on the part. So this asks:
;   Go on           the rest of the insert (or block) is skipped, the tool lifts straight
;                   up to the block's safe height, and the throat heats again
;   Stop the print  heatset/stop.g

var block = false
if exists(param.L)
  set var.block = param.L == 1
var what = "Heat-set insert " ^ global.hs_index
if var.block
  set var.what = "Heat-set block"

set global.hs_skip = true
if var.block
  set global.hs_block_skip = true
if global.hs_tool >= 0
  M568 P{global.hs_tool} A1
echo var.what ^ " stopped: " ^ param.S

M291 R{var.what} P{param.S ^ ". Go on lifts the tool clear and goes without it."} S4 K{"Go on","Stop the print"}
if input == 1
  M98 P"heatset/stop.g" S{param.S}

M400
G90
if global.hs_in_block && move.axes[2].userPosition < global.hs_z_safe
  G1 Z{global.hs_z_safe} F{global.hs_lift_feed}
if !var.block && global.hs_mode == "normal" && global.hs_tool >= 0
  M568 P{global.hs_tool} A2
