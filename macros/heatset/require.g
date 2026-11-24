; heatset/require.g: HEATSET_REQUIRE, in the header: what the whole print needs.
;
;   M98 P"heatset/require.g" K"<insert_key>" C<total_inserts> S<insert_temp>
;
; Before the first layer: the right key, the insert temperature within the limit, the
; follower homed, and enough inserts in the magazine (heatset/stock.g asks for a refill).

if !global.hs_configured
  abort "heatset/require.g: heatset/config.g has not run"
if param.K != global.hs_key
  abort "heatset/require.g: key " ^ param.K ^ " differs from the header's " ^ global.hs_key
if param.S <= 0 || param.S > global.hs_max_temp
  abort "heatset/require.g: " ^ param.S ^ " C is outside the limit of " ^ global.hs_max_temp ^ " C"
if param.C < 1
  abort "heatset/require.g: C must be 1 or more"

set global.hs_temp = param.S
set global.hs_left = param.C
if global.hs_mode == "normal"
  if !move.axes[global.hs_a].homed
    abort "heatset/require.g: home the follower (axis A) before printing"
  M98 P"heatset/stock.g" C{param.C} L2
echo "heatset: the print has " ^ param.C ^ " insert(s), at " ^ param.S ^ " C"
