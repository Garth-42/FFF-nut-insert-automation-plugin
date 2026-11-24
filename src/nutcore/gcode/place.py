"""Where an insert block goes after a layer.

Slicers label each object so that the firmware can cancel one mid-print: Klipper with
EXCLUDE_OBJECT_START / EXCLUDE_OBJECT_END, RepRapFirmware and Marlin with M486 S<n>
(S-1 for "no object"), and RepRapFirmware also from PrusaSlicer-style comment lines
("; printing object ..." / "; stop printing object ..."). While a cancelled object is
current, the firmware skips its moves, macro moves included. A block written inside an
object's label would lose its moves while its macro still runs, so a block goes after
the label that ends the object.

OrcaSlicer ends a layer with the last extrusion, the comment label, ";LAYER_CHANGE",
the retract, the wipe and, for Klipper, EXCLUDE_OBJECT_END. The block goes after all of
these, so the print tool has also retracted and wiped when it starts.
"""

from __future__ import annotations

import re

from .parser import Parsed

_OBJECT_START = re.compile(
    r"\s*(EXCLUDE_OBJECT_START\b|M486\s+S\d|;\s*printing object\b)", re.IGNORECASE)
_OBJECT_END = re.compile(
    r"\s*(EXCLUDE_OBJECT_END\b|M486\s+S-1\b|;\s*stop printing object\b)", re.IGNORECASE)
_MOVE = re.compile(r"(?:N\d+\s*)?G0*[0-3](?![\d.])", re.IGNORECASE)
# Firmware retraction: a bare G10 retracts and G11 primes. G10 with parameters is something
# else (tool offsets, or tool temperatures in RepRapFirmware).
_FW_RETRACT = re.compile(r"(?:N\d+\s*)?G10$", re.IGNORECASE)
_FW_PRIME = re.compile(r"(?:N\d+\s*)?G11(?![\d.])", re.IGNORECASE)
_TOOL = re.compile(r"(?:N\d+\s*)?T-?\d", re.IGNORECASE)
# Positioning or extruder mode changes, and homing: never carried into a block.
_MODE = re.compile(r"(?:N\d+\s*)?(G9[01]|M8[23]|G2[89])(?![\d.])", re.IGNORECASE)
# Lines that may come after the file's last extrusion without starting the end G-code.
_HARMLESS = re.compile(
    r"(?:N\d+\s*)?(G92|M73|M106|M107|M204|M205|M486|SET_VELOCITY_LIMIT)\b", re.IGNORECASE)


def block_after(parsed: Parsed, last: int) -> int:
    """The index of the line an insert block is written after.

    `last` is the layer's last extruding line. The block goes past what ends that layer:
    the slicer's retract (an E move or a firmware G10) and wipe and the label that closes
    the object. It stops before anything that starts the next layer: a move that changes
    Z, extrudes or primes, a G11, a label that opens an object, a tool change, or a change
    of positioning or extruder mode. Between layers, other commands (a timelapse macro, a
    temperature change) are passed over. After the file's last extrusion only harmless
    lines are, so the block never lands inside the end G-code.
    """
    lines, pos, de = parsed.lines, parsed.line_pos, parsed.line_de
    end_of_print = last >= parsed.last_extruding_line
    best = last
    for i in range(last + 1, len(lines)):
        text = lines[i]
        if _OBJECT_START.match(text):
            break
        if _OBJECT_END.match(text):
            best = i
            continue
        code = text.split(";", 1)[0].strip()
        if not code:
            continue                                   # a comment or a blank line
        if _FW_RETRACT.match(code):
            best = i
            continue
        if _FW_PRIME.match(code):
            break
        if _MOVE.match(code):
            if pos[i][2] != pos[i - 1][2] or de[i] > 0:
                break                                  # the next layer, extrusion or a prime
            if de[i] < 0:
                best = i                               # the retract or the wipe
            continue                                   # a travel or a feed rate
        if _TOOL.match(code) or _MODE.match(code):
            break
        if end_of_print and not _HARMLESS.match(code):
            break                                      # the end G-code starts here
    return best
