; heatset/init.g: set up the heat-set macros. RepRapFirmware 3.6 or later.
;
; Run it once from config.g, after the heat-set tool, the follower axis A and the float
; probe are defined:
;
;   M98 P"heatset/init.g"
;
; It declares the globals the macros share, loads the hard limits (heatset/limits.g),
; finds axis A, and reads the magazine kept across restarts (heatset/count.g, written by
; heatset/save.g). Running it again is safe. See macros/heatset/README.md.

if !exists(global.hs_ready)
  global hs_ready = false
  ; Hard limits and wiring: heatset/limits.g sets them.
  global hs_max_temp = 290.0
  global hs_max_push = 8.0
  global hs_max_unsheath = 2.0
  global hs_max_wait = 10.0
  global hs_max_speed = 5.0
  global hs_temp_settle = 60
  global hs_probe = 1
  global hs_lift_feed = 600
  ; Found here: the index of axis A in move.axes, -1 if there is none.
  global hs_a = -1
  ; This print: heatset/config.g and heatset/require.g.
  global hs_configured = false
  global hs_key = ""
  global hs_tool = -1
  global hs_pad_drop = 0.0
  global hs_overtravel = 0.0
  global hs_surface_tol = 0.0
  global hs_temp_window = 0.0
  global hs_on_proud = "warn"
  global hs_mode = "normal"
  global hs_rehearse_lift = 0.0
  global hs_temp = 0.0
  global hs_left = 0
  global hs_print_skip = false
  ; This block: heatset/begin.g to heatset/end.g.
  global hs_in_block = false
  global hs_block_skip = false
  global hs_prev_tool = -1
  global hs_z_safe = 0.0
  ; This insert: heatset/insert_start.g to heatset/insert_done.g.
  global hs_index = 0
  global hs_object = ""
  global hs_x = 0.0
  global hs_y = 0.0
  global hs_z_top = 0.0
  global hs_skip = false
  global hs_probed = false
  global hs_z_trip1 = 0.0
  global hs_s = 0.0
  global hs_waits = 0
  global hs_proud = 0.0
  ; The magazine, kept across restarts in heatset/count.g.
  global hs_count = 0
  global hs_loaded_key = ""
  global hs_pending_retract = 0.0

M98 P"heatset/limits.g"

set global.hs_a = -1
while iterations < #move.axes
  if move.axes[iterations].letter = "A"
    set global.hs_a = iterations
    break
if global.hs_a < 0
  echo "heatset: no axis A. Define the follower as axis A (M584), then run heatset/init.g"

if fileexists("0:/sys/heatset/count.g")
  M98 P"heatset/count.g"

set global.hs_ready = true
echo "heatset: ready. Magazine: " ^ global.hs_count ^ " " ^ global.hs_loaded_key
