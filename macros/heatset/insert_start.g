; heatset/insert_start.g: HEATSET_INSERT_START, step 1 of one insert.
;
;   M98 P"heatset/insert_start.g" I<index> O"<object>" X<x> Y<y> Z<z_top>
;
; Resets the insert's state. Skips the insert when its object is cancelled. Then checks
; the position, the magazine, the throat temperature and that the float reads open. Every
; routine macro after this does nothing while the insert is skipped.

if !global.hs_in_block
  abort "heatset/insert_start.g: outside a heatset/begin.g to heatset/end.g block"

set global.hs_index = param.I
set global.hs_object = param.O
set global.hs_x = param.X
set global.hs_y = param.Y
set global.hs_z_top = param.Z
set global.hs_skip = global.hs_block_skip
set global.hs_probed = false
set global.hs_waits = 0
set global.hs_proud = 0.0
if global.hs_skip
  echo "heatset: insert " ^ param.I ^ " skipped with its block"
  M99

var cancelled = false
if exists(job.build)
  if exists(job.build.objects)
    while iterations < #job.build.objects
      if job.build.objects[iterations].name == param.O
        set var.cancelled = job.build.objects[iterations].cancelled
        break
if var.cancelled
  set global.hs_skip = true
  echo "heatset: insert " ^ param.I ^ " skipped: object " ^ param.O ^ " is cancelled"
  M99

if param.X < move.axes[0].min || param.X > move.axes[0].max || param.Y < move.axes[1].min || param.Y > move.axes[1].max
  M98 P"heatset/fail.g" S{"X" ^ param.X ^ " Y" ^ param.Y ^ " is outside the printer's travel"}
  M99
M98 P"heatset/stock.g" C1
M98 P"heatset/heat.g"
if global.hs_skip || global.hs_mode != "normal"
  M99
if sensors.probes[global.hs_probe].value[0] >= sensors.probes[global.hs_probe].threshold
  M98 P"heatset/fail.g" S"the float reads tripped before the probe: stuck float or debris"
