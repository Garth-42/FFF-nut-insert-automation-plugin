; heatset/save.g: keep the magazine across restarts.
;
; Writes /sys/heatset/count.g, which heatset/init.g reads at start-up: how many inserts
; are left, which key they are, and the follower retract the next push takes up.

echo >"heatset/count.g" "; written by heatset/save.g: the heat-set magazine, read by heatset/init.g"
echo >>"heatset/count.g" "set global.hs_count = " ^ global.hs_count
echo >>"heatset/count.g" "set global.hs_loaded_key = """ ^ global.hs_loaded_key ^ """"
echo >>"heatset/count.g" "set global.hs_pending_retract = " ^ global.hs_pending_retract
