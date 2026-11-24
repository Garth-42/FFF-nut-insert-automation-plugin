; heatset/z.g: HEATSET_Z: the mouth to a height above the probed surface.
;
;   M98 P"heatset/z.g" H<height> V<speed>
;
; Moves the mouth to s + H at V mm/s, where s is the surface heatset/probe.g found (in
; rehearse mode, z_top + rehearse_lift).

if !global.hs_in_block
  abort "heatset/z.g: outside a heatset/begin.g to heatset/end.g block"
if global.hs_skip
  M99
if !global.hs_probed
  M98 P"heatset/fail.g" S"heatset/z.g ran before the surface was probed"
  M99
G90
G1 Z{global.hs_s + param.H} F{param.V * 60}
