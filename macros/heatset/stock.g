; heatset/stock.g: make sure the magazine holds enough inserts of the print's key.
;
;   M98 P"heatset/stock.g" C<needed>        for the current insert
;   M98 P"heatset/stock.g" C<needed> L1     for a block (heatset/begin.g)
;   M98 P"heatset/stock.g" C<needed> L2     for the whole print (heatset/require.g)
;
; While it is short, asks: Refilled (then how many are loaded now), Go on without (the
; insert, block or print goes without inserts), or Stop the print. Rehearse mode uses no
; inserts and does not check.

if global.hs_mode != "normal" || global.hs_skip
  M99

var level = 0
if exists(param.L)
  set var.level = param.L
var have = 0
if global.hs_loaded_key == global.hs_key
  set var.have = global.hs_count

while var.have < param.C
  M291 R"Heat-set magazine" P{"Needs " ^ param.C ^ " " ^ global.hs_key ^ " inserts and has " ^ var.have ^ "."} S4 K{"Refilled","Go on without","Stop the print"}
  if input == 2
    M98 P"heatset/stop.g" S{"the magazine is short of " ^ global.hs_key ^ " inserts"}
  if input == 1
    set global.hs_skip = true
    if var.level >= 1
      set global.hs_block_skip = true
    if var.level >= 2
      set global.hs_print_skip = true
    echo "heatset: going on without inserts: the magazine is short"
    break
  M291 R"Heat-set magazine" P{"How many " ^ global.hs_key ^ " inserts are in the magazine now?"} S5 L0 H999 F{param.C}
  set global.hs_count = input
  set global.hs_loaded_key = global.hs_key
  M98 P"heatset/save.g"
  set var.have = global.hs_count
