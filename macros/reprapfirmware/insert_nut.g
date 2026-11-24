; insert_nut.g: nut insert, DRY RUN, for RepRapFirmware 3.6 or later.
;
; The nut inserter plugin for OrcaSlicer writes one line per nut into the G-code:
;
;   M98 P"insert_nut.g" K"M3SQ" C"FLAT" X164.706 Y158.320 Z1.900 L1.000 A0.00 F1 S0
;
; This macro places nothing. It checks the values, reports them, and pauses the
; print, so you can see that every nut is called at the right layer and position
; before a real nut tool is involved. Resume continues the print.
;
; It has not been run on a printer. Try it first with a small test print and a
; hand near the emergency stop.
;
; Requirements:
;   - RepRapFirmware 3.6 or later. It uses macro parameters and meta commands.
;   - /sys/pause.g and /sys/resume.g. pause.g retracts and parks the print tool;
;     resume.g brings it back to where it stopped and undoes its own retraction.
;
; Install: upload this file to /sys/ on the printer (Duet Web Control, System).
; The G-code calls it by name, and M98 looks for a relative name in /sys/.
;
; When the block runs, the slicer has normally retracted and wiped the print
; tool after the layer, and no object label is open. A real macro must bring the
; print tool back to the same position, undo any retraction it adds itself, and
; leave the positioning and extruder modes as it found them.
;
; A pause asked for inside a macro takes effect when the macro ends, so the print
; stops right after this nut's line.
;
; What the values mean (bed coordinates, mm, as printed):
;   K     nut type key from the nut library, for example M3SQ
;   C     FLAT, EDGE or CORNER
;   X, Y  centre of the pocket
;   Z     centre of the seated nut
;   L     lowest point of the seated nut: the pocket floor for a flat nut
;   A     FLAT: rotation of the flats about Z, 0 to 90 degrees
;         EDGE or CORNER: heading of the thread axis, 0 to 180 degrees
;   F     feeder number from the nut library
;   S     the print tool that was active, or -1 if the file never selected one

if !exists(param.K) || !exists(param.C) || !exists(param.X) || !exists(param.Y) || !exists(param.Z)
  abort "insert_nut.g: K, C, X, Y and Z are required"
if !exists(param.L) || !exists(param.A) || !exists(param.F) || !exists(param.S)
  abort "insert_nut.g: L, A, F and S are required"
if param.X < move.axes[0].min || param.X > move.axes[0].max || param.Y < move.axes[1].min || param.Y > move.axes[1].max
  abort "insert_nut.g: X" ^ param.X ^ " Y" ^ param.Y ^ " is outside the printer's travel"
if param.L < 0 || param.Z < param.L
  abort "insert_nut.g: Z" ^ param.Z ^ " and L" ^ param.L ^ " do not make sense"
if move.axes[2].userPosition < param.Z
  abort "insert_nut.g: the nozzle is at Z" ^ move.axes[2].userPosition ^ ", below the nut centre Z" ^ param.Z

echo "insert_nut.g dry run: " ^ param.K ^ " " ^ param.C ^ ", pocket centre X" ^ param.X ^ " Y" ^ param.Y
echo "  nut centre Z" ^ param.Z ^ ", lowest point Z" ^ param.L ^ ", angle " ^ param.A ^ ", feeder " ^ param.F ^ ", print tool " ^ param.S
echo "  nozzle at Z" ^ move.axes[2].userPosition ^ ". Pausing: resume to continue."
M291 P{"Nut " ^ param.K ^ " " ^ param.C ^ " at X" ^ param.X ^ " Y" ^ param.Y ^ " Z" ^ param.Z ^ ". Resume to continue."} R"Nut insert dry run" S1 T0
M226

; Outline of the real macro, for when the nut tool exists. Not usable as is.
;
;   M120                                   ; push the state: positioning, extruder mode, speed
;   ... retract the print tool and lift it clear of the part ...
;   T<nut tool>                            ; tfree/tpre/tpost run; pick a nut from feeder F
;   G90
;   G0 X{param.X} Y{param.Y}               ; the nut tool's offset is applied by RRF
;   ... turn the nut to angle A, lower it to Z or L, release, check the seat ...
;   T T{param.S}                           ; back to the print tool, undo the retraction
;   M121                                   ; pop the state
