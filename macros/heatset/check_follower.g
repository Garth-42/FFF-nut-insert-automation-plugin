; heatset/check_follower.g: bring-up: move the follower (axis A) forward, then back.
;
;   M98 P"heatset/check_follower.g" D1 V1
;
; D: mm forward and back (default 1). V: mm/s (default 1). Asks before it moves. Watch that
; +A pushes the stack toward the mouth, 1 mm per mm. Run it with the magazine empty, or
; with the mouth where a pushed insert can do no harm.

if !exists(global.hs_ready)
  abort "heatset/check_follower.g: run heatset/init.g first, from config.g"
if global.hs_a < 0
  abort "heatset/check_follower.g: there is no axis A for the follower (M584)"

var d = 1.0
if exists(param.D)
  set var.d = param.D
var v = 1.0
if exists(param.V)
  set var.v = param.V
if var.d <= 0 || var.d > global.hs_max_push || var.v <= 0
  abort "heatset/check_follower.g: D must be over 0 and at most " ^ global.hs_max_push ^ " mm, V over 0"
if !move.axes[global.hs_a].homed
  abort "heatset/check_follower.g: home the follower (axis A) first"

M400
var start = move.axes[global.hs_a].userPosition
if var.start + var.d > move.axes[global.hs_a].max
  abort "heatset/check_follower.g: A" ^ var.start ^ " + " ^ var.d ^ " would pass the axis A maximum"
M291 R"Follower check" P{"Moves the follower " ^ var.d ^ " mm forward, then back. Go?"} S4 K{"Move","Cancel"}
if input == 1
  M99

G91
G1 A{var.d} F{var.v * 60}
M400
var there = move.axes[global.hs_a].userPosition
G1 A{-var.d} F{var.v * 60}
G90
M400
echo "heatset follower: A " ^ var.start ^ " to " ^ var.there ^ " and back to " ^ move.axes[global.hs_a].userPosition
