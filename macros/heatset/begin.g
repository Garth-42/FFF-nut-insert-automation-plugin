; heatset/begin.g: HEATSET_BEGIN, the start of a block of inserts.
;
;   M98 P"heatset/begin.g" K"<insert_key>" S<insert_temp> Z<z_safe> C<inserts_in_block>
;
; Lifts to Z (never down), remembers the print tool, selects the heat-set tool, waits for
; the throat (heatset/heat.g) and checks the magazine (heatset/stock.g). In rehearse mode
; the throat stays off. A print going without inserts skips the block but keeps the
; print tool, so the block's own moves run with it, at the block's heights.

if !global.hs_configured
  abort "heatset/begin.g: heatset/config.g has not run"
if global.hs_in_block
  abort "heatset/begin.g: the last block never ended (heatset/end.g)"
if param.K != global.hs_key
  abort "heatset/begin.g: key " ^ param.K ^ " differs from the header's " ^ global.hs_key
if param.S <= 0 || param.S > global.hs_max_temp
  abort "heatset/begin.g: " ^ param.S ^ " C is outside the limit of " ^ global.hs_max_temp ^ " C"

set global.hs_in_block = true
set global.hs_block_skip = global.hs_print_skip
set global.hs_skip = global.hs_print_skip
set global.hs_z_safe = param.Z
set global.hs_temp = param.S
set global.hs_prev_tool = state.currentTool
if global.hs_print_skip
  M99

M400
G90
if move.axes[2].userPosition < param.Z
  G1 Z{param.Z} F{global.hs_lift_feed}
if global.hs_mode == "normal"
  M568 P{global.hs_tool} S{param.S}
else
  M568 P{global.hs_tool} R0 S0
T T{global.hs_tool}
if global.hs_mode != "normal"
  M568 P{global.hs_tool} A0

M98 P"heatset/heat.g" L1
M98 P"heatset/stock.g" C{param.C} L1
echo "heatset: block of " ^ param.C ^ " insert(s), " ^ global.hs_mode ^ " mode"
