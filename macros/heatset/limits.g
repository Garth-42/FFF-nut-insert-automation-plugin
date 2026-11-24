; heatset/limits.g: the printer's hard limits for the heat-set tool, and its wiring.
;
; Edit the values here, never in G-code. The G-code passes thresholds and these cap them
; (docs/HEATSET_GCODE_SPEC.md, "Failures and safety limits"). heatset/init.g runs this
; file at start-up; run it again after an edit:  M98 P"heatset/limits.g"

set global.hs_max_temp = 290.0     ; C: the throat at most. Keep the heater's M143 limit at or below it
set global.hs_max_push = 8.0       ; mm of axis A in one push
set global.hs_max_unsheath = 2.0   ; mm in one unsheath move, and in one follower retract
set global.hs_max_wait = 10.0      ; s: any dwell or wait the G-code asks for
set global.hs_max_speed = 5.0      ; mm/s: probe and press speeds
set global.hs_temp_settle = 60     ; s to reach the insert temperature before asking what to do
set global.hs_probe = 1            ; TBD: the float's probe number, as in M558 K<n>
set global.hs_lift_feed = 600      ; mm/min: lifts the macros make on their own
