"""A small G-code reader: moves, extrusion, tool and position per line.

It never depends on slicer comment lines. Every line is kept as it was, with
its line ending, so the file can be written back unchanged.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

import numpy as np

ARC_CHORD = 0.5  # mm, longest straight piece of a split arc

_COMMAND = re.compile(r"^(?:N\d+\s*)?([GMT])(\d+)(?:\.\d+)?(?![_\d])", re.IGNORECASE)
_WORD = re.compile(r"([A-Za-z])\s*([-+]?(?:\d+\.?\d*|\.\d+))")


@dataclass
class Parsed:
    lines: list[str]            # the file's lines, endings included
    newline: str                # the file's line ending
    seg: np.ndarray             # (K, 6) x0, y0, z0, x1, y1, z1 of every move piece
    seg_line: np.ndarray        # (K,) index of the line a piece came from
    seg_extruding: np.ndarray   # (K,) True when E grows while X or Y changes
    line_tool: np.ndarray       # (L,) active tool after each line, -1 if none seen
    line_pos: np.ndarray        # (L, 3) nozzle position after each line

    @property
    def extruding(self) -> np.ndarray:
        """The extruding pieces only: (segments, line indices)."""
        return self.seg[self.seg_extruding], self.seg_line[self.seg_extruding]


def parse(text: str) -> Parsed:
    lines = text.splitlines(keepends=True)
    newline = "\r\n" if lines and lines[0].endswith("\r\n") else "\n"
    pos = [0.0, 0.0, 0.0]
    e = 0.0
    absolute, absolute_e = True, True
    tool = -1
    seg, seg_line, seg_ext = [], [], []
    line_tool = np.full(len(lines), -1, dtype=np.int32)
    line_pos = np.zeros((len(lines), 3))

    for i, raw in enumerate(lines):
        code = raw.split(";", 1)[0].strip()
        found = _COMMAND.match(code) if code else None
        if found:
            letter, number = found.group(1).upper(), int(found.group(2))
            if letter == "T":
                tool = number
            elif letter == "M":
                if number == 82:
                    absolute_e = True
                elif number == 83:
                    absolute_e = False
            elif number in (0, 1, 2, 3):
                words = {k.upper(): float(v) for k, v in _WORD.findall(code[found.end():])}
                target = list(pos)
                for axis, name in enumerate("XYZ"):
                    if name in words:
                        target[axis] = words[name] if absolute else pos[axis] + words[name]
                delta_e = 0.0
                if "E" in words:
                    delta_e = words["E"] - e if absolute_e else words["E"]
                    e = words["E"] if absolute_e else e + words["E"]
                moved_xy = target[0] != pos[0] or target[1] != pos[1]
                arc = number in (2, 3) and ("I" in words or "J" in words)
                if moved_xy or target[2] != pos[2] or arc:
                    extruding = delta_e > 1e-9 and (moved_xy or arc)
                    if arc:
                        pieces = _arc(pos, target, words.get("I", 0.0), words.get("J", 0.0),
                                      clockwise=number == 2)
                    else:
                        pieces = [(*pos, *target)]
                    seg.extend(pieces)
                    seg_line.extend([i] * len(pieces))
                    seg_ext.extend([extruding] * len(pieces))
                pos = target
            elif number == 90:
                absolute = True
            elif number == 91:
                absolute = False
            elif number == 92:
                words = {k.upper(): float(v) for k, v in _WORD.findall(code[found.end():])}
                for axis, name in enumerate("XYZ"):
                    if name in words:
                        pos[axis] = words[name]
                if "E" in words:
                    e = words["E"]
        line_tool[i] = tool
        line_pos[i] = pos

    return Parsed(lines=lines, newline=newline,
                  seg=np.array(seg, dtype=np.float64).reshape(-1, 6),
                  seg_line=np.array(seg_line, dtype=np.int64),
                  seg_extruding=np.array(seg_ext, dtype=bool),
                  line_tool=line_tool, line_pos=line_pos)


def _arc(start, end, i, j, clockwise) -> list[tuple]:
    """Split a G2/G3 arc in I, J form into straight pieces of at most ARC_CHORD."""
    cx, cy = start[0] + i, start[1] + j
    radius = math.hypot(i, j)
    a0 = math.atan2(start[1] - cy, start[0] - cx)
    a1 = math.atan2(end[1] - cy, end[0] - cx)
    sweep = a1 - a0
    if clockwise:
        if sweep >= -1e-12:
            sweep -= 2 * math.pi       # same start and end point: a full circle
    elif sweep <= 1e-12:
        sweep += 2 * math.pi
    count = max(1, math.ceil(abs(sweep) * radius / ARC_CHORD))
    pieces = []
    previous = tuple(start)
    for k in range(1, count + 1):
        f = k / count
        if k == count:
            point = tuple(end)
        else:
            angle = a0 + sweep * f
            point = (cx + radius * math.cos(angle), cy + radius * math.sin(angle),
                     start[2] + (end[2] - start[2]) * f)
        pieces.append((*previous, *point))
        previous = point
    return pieces
