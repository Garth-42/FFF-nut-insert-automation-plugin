; HEATSET block 1: end_of_print, inserts=1, key M3x5.7
M98 P"heatset/begin.g" K"M3x5.7" S245 Z17.400 C1
; insert 1/1 bracket_1 X120.000 Y80.000 Ztop12.400
M98 P"heatset/insert_start.g" I1 O"bracket_1" X120.000 Y80.000 Z12.400
G90
G0 Z17.400 F600
G0 X100.000 Y80.000 F9000
G0 Z14.800 F300
M98 P"heatset/probe.g" V2.0
M98 P"heatset/z.g" H3.000 V5.0
G0 X120.000 Y80.000 F1800
M98 P"heatset/z.g" H0.800 V5.0
M98 P"heatset/push.g" D5.400 V0.5 W2.0 C3
M98 P"heatset/unsheath.g" D0.300 V1.0
M98 P"heatset/retract.g" D0.300 V2.0
M98 P"heatset/z.g" H2.600 V5.0
G0 X100.000 Y80.000 F1800
M98 P"heatset/press.g" V1.0 W3.0 U0.100 L0.300
M98 P"heatset/z.g" H3.000 V5.0
M98 P"heatset/insert_done.g"
M98 P"heatset/end.g"
