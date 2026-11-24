; heatset/config.g: HEATSET_CONFIG, the first heat-set line of a print (in its header).
;
;   M98 P"heatset/config.g" K"<insert_key>" H<tool> D<pad_drop> O<trip_overtravel>
;       U<surface_tol> W<temp_window> Q"<on_proud>" B"<mode>" L<rehearse_lift>
;
; Checks the values against the printer and keeps them for this print. Anything wrong
; ends the print here, before anything is printed. Not to be confused with /sys/config.g:
; this file lives in /sys/heatset/.

if !exists(global.hs_ready)
  abort "heatset: add M98 P""heatset/init.g"" to the end of /sys/config.g, then restart"
if !exists(param.K) || !exists(param.H) || !exists(param.D) || !exists(param.O) || !exists(param.U)
  abort "heatset/config.g: K, H, D, O and U are required"
if !exists(param.W) || !exists(param.Q) || !exists(param.B) || !exists(param.L)
  abort "heatset/config.g: W, Q, B and L are required"
if param.B != "normal" && param.B != "rehearse"
  abort "heatset/config.g: B (mode) must be normal or rehearse"
if param.Q != "warn" && param.Q != "pause"
  abort "heatset/config.g: Q (on_proud) must be warn or pause"
if param.D <= 0 || param.O < 0 || param.U <= 0 || param.W <= 0 || param.L < 0
  abort "heatset/config.g: D, U and W must be more than 0, O and L 0 or more"
if !exists(tools[param.H])
  abort "heatset/config.g: tool " ^ param.H ^ " is not defined (M563)"
if tools[param.H] == null
  abort "heatset/config.g: tool " ^ param.H ^ " is not defined (M563)"
if #tools[param.H].heaters < 1
  abort "heatset/config.g: tool " ^ param.H ^ " has no heater for the throat"
if global.hs_a < 0
  abort "heatset/config.g: there is no axis A for the follower (M584)"
if !exists(sensors.probes[global.hs_probe])
  abort "heatset/config.g: probe " ^ global.hs_probe ^ ", the float in heatset/limits.g, is not defined"
if sensors.probes[global.hs_probe] == null
  abort "heatset/config.g: probe " ^ global.hs_probe ^ ", the float in heatset/limits.g, is not defined"

set global.hs_key = param.K
set global.hs_tool = param.H
set global.hs_pad_drop = param.D
set global.hs_overtravel = param.O
set global.hs_surface_tol = param.U
set global.hs_temp_window = param.W
set global.hs_on_proud = param.Q
set global.hs_mode = param.B
set global.hs_rehearse_lift = param.L
set global.hs_temp = 0.0
set global.hs_left = 0
set global.hs_print_skip = false
set global.hs_in_block = false
set global.hs_block_skip = false
set global.hs_skip = false
set global.hs_configured = true
echo "heatset: " ^ param.B ^ " mode, key " ^ param.K ^ ", tool " ^ param.H
