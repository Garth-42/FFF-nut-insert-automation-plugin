; heatset/heat.g: wait for the throat to reach the insert temperature.
;
;   M98 P"heatset/heat.g"        for the current insert
;   M98 P"heatset/heat.g" L1     for the whole block (from heatset/begin.g)
;
; Waits until the throat is within temp_window of the insert temperature, up to
; hs_temp_settle seconds (heatset/limits.g), then asks what to do (heatset/fail.g).
; Rehearse mode keeps the heater off and does not wait.

if global.hs_mode != "normal" || global.hs_skip
  M99

var heater = tools[global.hs_tool].heaters[0]
var level = 0
if exists(param.L)
  set var.level = param.L
while abs(heat.heaters[var.heater].current - global.hs_temp) > global.hs_temp_window
  if iterations >= global.hs_temp_settle
    var why = "throat at " ^ heat.heaters[var.heater].current ^ " C, needs " ^ global.hs_temp ^ " C"
    M98 P"heatset/fail.g" S{var.why} L{var.level}
    break
  G4 S1
