; heatset/probe.g: HEATSET_PROBE, step 4: find the surface around the hole.
;
;   M98 P"heatset/probe.g" V<probe_speed>
;
; With the pad over the hole, lowers until the float trips (G38.3, never further than
; surface_tol below the expected trip), then takes the surface as
; s = z_trip1 + trip_overtravel - pad_drop. Refuses when s is more than surface_tol from
; z_top, before heat touches the part. Rehearse mode does not probe: s is z_top plus
; rehearse_lift, so every later height stays that far above the part.

if !global.hs_in_block
  abort "heatset/probe.g: outside a heatset/begin.g to heatset/end.g block"
if global.hs_skip
  M99

var p = global.hs_pad_drop
if global.hs_mode != "normal"
  set global.hs_s = global.hs_z_top + global.hs_rehearse_lift
  set global.hs_z_trip1 = global.hs_s - global.hs_overtravel + var.p
  set global.hs_probed = true
  echo "heatset: insert " ^ global.hs_index ^ ", rehearse: surface taken as Z" ^ global.hs_s
  M99

var k = global.hs_probe
if sensors.probes[var.k].value[0] >= sensors.probes[var.k].threshold
  M98 P"heatset/fail.g" S"the float reads tripped before the probe: stuck float or debris"
  M99
var speed = min(param.V, global.hs_max_speed)
var lowest = global.hs_z_top + var.p - global.hs_overtravel - global.hs_surface_tol - 0.05
M400
G38.3 K{var.k} Z{var.lowest} F{var.speed * 60}
M400
set global.hs_z_trip1 = move.axes[2].userPosition
if sensors.probes[var.k].value[0] < sensors.probes[var.k].threshold
  M98 P"heatset/fail.g" S{"the float did not trip down to Z" ^ var.lowest ^ ": no surface under the pad"}
  M99
set global.hs_s = global.hs_z_trip1 + global.hs_overtravel - var.p
set global.hs_probed = true
if abs(global.hs_s - global.hs_z_top) > global.hs_surface_tol
  M98 P"heatset/fail.g" S{"surface at Z" ^ global.hs_s ^ ", not Z" ^ global.hs_z_top ^ ": part moved or warped?"}
