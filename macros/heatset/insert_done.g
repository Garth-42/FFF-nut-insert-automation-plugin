; heatset/insert_done.g: HEATSET_INSERT_DONE, step 11: count the insert and log it.
;
;   M98 P"heatset/insert_done.g"
;
; The G-code has already lifted the mouth to local_clear. Counts the insert out of the
; magazine (not in rehearse mode, and not when it was skipped), keeps the count
; (heatset/save.g), and logs one line to the console and to /sys/heatset/log.csv:
; index, key, X, Y, s - z_top, waits, proud, and what happened.

if !global.hs_in_block
  abort "heatset/insert_done.g: outside a heatset/begin.g to heatset/end.g block"

set global.hs_left = global.hs_left - 1
var outcome = "done"
if global.hs_skip
  set var.outcome = "skipped"
elif global.hs_mode != "normal"
  set var.outcome = "rehearsed"
else
  set global.hs_count = global.hs_count - 1
  M98 P"heatset/save.g"

var offset = 0.0
if global.hs_probed
  set var.offset = global.hs_s - global.hs_z_top
echo "heatset: insert " ^ global.hs_index ^ " " ^ var.outcome ^ ", " ^ global.hs_key ^ " X" ^ global.hs_x ^ " Y" ^ global.hs_y
echo "  surface " ^ var.offset ^ " mm from z_top, waits " ^ global.hs_waits ^ ", proud " ^ global.hs_proud ^ " mm"
if !fileexists("0:/sys/heatset/log.csv")
  echo >"heatset/log.csv" "index,key,x,y,surface_minus_z_top,waits,proud,outcome"
var row = global.hs_index ^ "," ^ global.hs_key ^ "," ^ global.hs_x ^ "," ^ global.hs_y ^ "," ^ var.offset
echo >>"heatset/log.csv" var.row ^ "," ^ global.hs_waits ^ "," ^ global.hs_proud ^ "," ^ var.outcome
set global.hs_skip = global.hs_block_skip
