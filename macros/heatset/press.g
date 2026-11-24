; heatset/press.g: HEATSET_PRESS, step 10: the cold press with the pad over the insert.
;
;   M98 P"heatset/press.g" V<press_speed> W<press_dwell> U<flush_tol> L<press_guard>
;
; The float must read open. Lowers until it trips (G38.3, never more than L + 0.5 mm
; below where it tripped on the surface), holds W seconds, then compares:
; proud = z_trip2 - z_trip1, as the pad drop and trip overtravel cancel. Over U runs
; on_proud: warn, or pause (ask whether to go on). Under -L warns of an overpress.
; Rehearse mode lowers the pad face to s (rehearse_lift above the part) and dwells.

if !global.hs_in_block
  abort "heatset/press.g: outside a heatset/begin.g to heatset/end.g block"
if global.hs_skip
  M99
if !global.hs_probed
  M98 P"heatset/fail.g" S"heatset/press.g ran before the surface was probed"
  M99

var dwell = min(param.W, global.hs_max_wait)
var speed = min(param.V, global.hs_max_speed)
if global.hs_mode != "normal"
  G90
  G1 Z{global.hs_s + global.hs_pad_drop} F{var.speed * 60}
  G4 S{var.dwell}
  set global.hs_proud = 0.0
  M99

var k = global.hs_probe
if sensors.probes[var.k].value[0] >= sensors.probes[var.k].threshold
  M98 P"heatset/fail.g" S"the float reads tripped before the press: stuck float or debris"
  M99
var lowest = global.hs_z_trip1 - param.L - 0.5
M400
G38.3 K{var.k} Z{var.lowest} F{var.speed * 60}
M400
var trip2 = move.axes[2].userPosition
if sensors.probes[var.k].value[0] < sensors.probes[var.k].threshold
  M98 P"heatset/fail.g" S{"the press met nothing down to Z" ^ var.lowest ^ ": is the insert there?"}
  M99
G4 S{var.dwell}
set global.hs_proud = var.trip2 - global.hs_z_trip1

var why = "insert " ^ global.hs_index ^ " is " ^ global.hs_proud ^ " mm proud, over " ^ param.U ^ " mm"
if global.hs_proud > param.U
  echo "heatset: " ^ var.why
  if global.hs_on_proud == "pause"
    M291 R"Heat-set insert" P{var.why ^ ". Go on, or stop the print?"} S4 K{"Go on","Stop the print"}
    if input == 1
      M98 P"heatset/stop.g" S{var.why}
  else
    M291 R"Heat-set insert" P{var.why} S1 T10
elif global.hs_proud < -param.L
  set var.why = "insert " ^ global.hs_index ^ " pressed " ^ (-global.hs_proud) ^ " mm below the surface"
  echo "heatset: " ^ var.why ^ ": plastic too soft, or trip_overtravel wrong?"
  M291 R"Heat-set insert" P{var.why} S1 T10
