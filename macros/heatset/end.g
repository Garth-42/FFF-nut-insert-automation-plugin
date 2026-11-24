; heatset/end.g: HEATSET_END, the end of a block.
;
;   M98 P"heatset/end.g"
;
; Lifts to the block's safe height and selects the tool that was printing before the
; block. Deselecting the heat-set tool puts its throat at standby; after the print's last
; insert it is turned off.

if !global.hs_in_block
  abort "heatset/end.g: no block to end (heatset/begin.g)"

M400
G90
if move.axes[2].userPosition < global.hs_z_safe
  G1 Z{global.hs_z_safe} F{global.hs_lift_feed}
if state.currentTool != global.hs_prev_tool
  if global.hs_prev_tool >= 0
    T T{global.hs_prev_tool}
  else
    T-1
if global.hs_left <= 0
  M568 P{global.hs_tool} A0

set global.hs_in_block = false
set global.hs_block_skip = false
set global.hs_skip = false
