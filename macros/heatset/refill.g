; heatset/refill.g: tell the macros what the magazine holds, after loading it.
;
;   M98 P"heatset/refill.g" K"M3x5.7" C12
;
; K: the insert key loaded, as in the heat-set profile. C: how many inserts.
; Run it from the console. The print G-code never calls it.

if !exists(global.hs_ready)
  abort "heatset/refill.g: run heatset/init.g first, from config.g"
if !exists(param.K) || !exists(param.C)
  abort "heatset/refill.g: K (the insert key) and C (how many) are required"
if param.C < 0
  abort "heatset/refill.g: C must be 0 or more"

set global.hs_loaded_key = param.K
set global.hs_count = param.C
M98 P"heatset/save.g"
echo "heatset: the magazine holds " ^ global.hs_count ^ " " ^ global.hs_loaded_key
