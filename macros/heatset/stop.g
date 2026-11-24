; heatset/stop.g: end the print from a heat-set dialog.
;
;   M98 P"heatset/stop.g" S"<reason>"
;
; Turns the throat and the print tool's heater off, then ends the print with abort.
; The bed and anything else stay as they are.

if global.hs_tool >= 0
  M568 P{global.hs_tool} A0
if global.hs_in_block && global.hs_prev_tool >= 0
  M568 P{global.hs_prev_tool} A0
if state.currentTool >= 0 && state.currentTool != global.hs_tool
  M568 P{state.currentTool} A0
abort "Heat-set: print stopped. " ^ param.S
