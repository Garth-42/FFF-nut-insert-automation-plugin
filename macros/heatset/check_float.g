; heatset/check_float.g: bring-up: does the float read open, and trip when pushed?
;
;   M98 P"heatset/check_float.g"
;
; Reads the float (probe hs_probe in heatset/limits.g) with nothing touching it, then
; gives you 15 seconds to push it up by hand and watches for the trip. Run it again with
; the float unplugged: it must then read tripped at once, so a broken wire stops the tool.
; Nothing moves.

if !exists(global.hs_ready)
  abort "heatset/check_float.g: run heatset/init.g first, from config.g"
if !exists(sensors.probes[global.hs_probe])
  abort "heatset/check_float.g: probe " ^ global.hs_probe ^ " (heatset/limits.g) is not defined"

var k = global.hs_probe
var threshold = sensors.probes[var.k].threshold
var free = sensors.probes[var.k].value[0]
echo "heatset float: reads " ^ var.free ^ " with nothing touching it, threshold " ^ var.threshold
if var.free >= var.threshold
  echo "heatset float: reads TRIPPED. Right if it is unplugged, otherwise it is stuck or inverted"
  M99

M291 R"Float check" P"Push the float up by hand within 15 seconds." S1 T15
var seen = false
while iterations < 150
  if sensors.probes[var.k].value[0] >= var.threshold
    set var.seen = true
    break
  G4 P100
if var.seen
  echo "heatset float: OK, open when free and tripped when pushed. Now unplug it and run this again"
else
  echo "heatset float: did not trip in 15 seconds. Check its wiring and the M558 settings"
