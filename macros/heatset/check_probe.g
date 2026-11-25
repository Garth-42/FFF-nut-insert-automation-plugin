; heatset/check_probe.g: bring-up: probe down with the float and report where it tripped.
;
;   M98 P"heatset/check_probe.g" D5 V1
;
; Select the heat-set tool and put its pad a few mm over a flat, solid plate first. Lowers
; at most D mm (default 5) at V mm/s (default 1, at most the limit's probe speed) until the
; float trips, reports the height, and goes back up to where it started. Run it a few times
; to see how repeatable the trip is. Asks before it moves.

if !exists(global.hs_ready)
  abort "heatset/check_probe.g: run heatset/init.g first, from config.g"
if !exists(sensors.probes[global.hs_probe])
  abort "heatset/check_probe.g: probe " ^ global.hs_probe ^ " (heatset/limits.g) is not defined"

var k = global.hs_probe
var d = 5.0
if exists(param.D)
  set var.d = param.D
var v = 1.0
if exists(param.V)
  set var.v = param.V
set var.v = min(var.v, global.hs_max_speed)
if var.d <= 0 || var.v <= 0
  abort "heatset/check_probe.g: D and V must be over 0"
if sensors.probes[var.k].value[0] >= sensors.probes[var.k].threshold
  abort "heatset/check_probe.g: the float reads tripped already. Run heatset/check_float.g"

M400
var start = move.axes[2].userPosition
var lowest = var.start - var.d
if var.lowest < move.axes[2].min
  abort "heatset/check_probe.g: Z" ^ var.lowest ^ " is below the Z minimum. Start higher or lower D"
M291 R"Probe check" P{"Lowers at most " ^ var.d ^ " mm until the float trips. Pad over a plate?"} S4 K{"Probe","Cancel"}
if input == 1
  M99

G38.3 K{var.k} Z{var.lowest} F{var.v * 60}
M400
var trip = move.axes[2].userPosition
var tripped = sensors.probes[var.k].value[0] >= sensors.probes[var.k].threshold
G90
G1 Z{var.start} F{global.hs_lift_feed}
if var.tripped
  echo "heatset probe: tripped at Z" ^ var.trip ^ ", " ^ (var.start - var.trip) ^ " mm below the start"
else
  echo "heatset probe: did not trip within " ^ var.d ^ " mm"
