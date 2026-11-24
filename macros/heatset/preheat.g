; heatset/preheat.g: HEATSET_PREHEAT: start heating the throat ahead of a block.
;
;   M98 P"heatset/preheat.g" S<insert_temp>
;
; Sets the heat-set tool's active temperature and turns it on, without selecting the tool
; and without waiting, while the print tool goes on printing. Rehearse mode leaves it off.

if !global.hs_configured
  abort "heatset/preheat.g: heatset/config.g has not run"
if param.S <= 0 || param.S > global.hs_max_temp
  abort "heatset/preheat.g: " ^ param.S ^ " C is outside the limit of " ^ global.hs_max_temp ^ " C"
if global.hs_mode != "normal" || global.hs_print_skip
  M99
M568 P{global.hs_tool} S{param.S} A2
