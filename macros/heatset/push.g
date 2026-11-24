; heatset/push.g: the hot push, step 6: the spec's _HS_PUSH_START, ticks and _HS_PUSH_END.
;
;   M98 P"heatset/push.g" D<push> V<push_speed> W<resist_wait> C<resist_retries>
;
; Feeds the follower (axis A) by D, after taking up any pending retract, with G38.3 so it
; stops when the float trips. A trip means the insert resists: wait W seconds and go on,
; at most C waits, then stop (heatset/fail.g). The retract still pending afterwards is
; kept (heatset/save.g). Rehearse mode never moves A.

if !global.hs_in_block
  abort "heatset/push.g: outside a heatset/begin.g to heatset/end.g block"
if global.hs_skip
  M99
if global.hs_mode != "normal"
  echo "heatset: insert " ^ global.hs_index ^ ", rehearse: push of " ^ param.D ^ " mm left out"
  M99
if param.D <= 0 || param.D > global.hs_max_push
  M98 P"heatset/fail.g" S{"a push of " ^ param.D ^ " mm is over the limit of " ^ global.hs_max_push ^ " mm"}
  M99

var k = global.hs_probe
var a = global.hs_a
M400
var start = move.axes[var.a].userPosition
var target = var.start + global.hs_pending_retract + param.D
if var.target > move.axes[var.a].max
  M98 P"heatset/fail.g" S"the follower would pass its end (axis A maximum): refill the magazine"
  M99
var wait = min(param.W, global.hs_max_wait)
var tries = {2 * param.C + 4}
set global.hs_waits = 0

while true
  if iterations >= var.tries
    M98 P"heatset/fail.g" S"the push did not finish"
    break
  if sensors.probes[var.k].value[0] >= sensors.probes[var.k].threshold
    if global.hs_waits >= param.C
      M98 P"heatset/fail.g" S{"the insert still resists after " ^ param.C ^ " waits"}
      break
    set global.hs_waits = global.hs_waits + 1
    G4 S{var.wait}
    continue
  G38.3 K{var.k} A{var.target} F{param.V * 60}
  M400
  if abs(move.axes[var.a].userPosition - var.target) < 0.001
    break

; Whatever happened, the follower has taken up as much of the retract as it moved.
M400
set global.hs_pending_retract = max(0.0, var.start + global.hs_pending_retract - move.axes[var.a].userPosition)
M98 P"heatset/save.g"
