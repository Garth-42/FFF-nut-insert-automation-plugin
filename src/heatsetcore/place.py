"""Where the heat-set lines go in an exported G-code file, and what stops an insert.

docs/HEATSET_GCODE_SPEC.md, "Emitted G-code" (placement) and "Validation"; docs/heatset-
plan.md, "Found in a real Orca export" and "Export". Each insert is planned on the G-code
alone, like the nut proof: its local layers, the printed surface, the empty-hole proof,
its block point and the keep-out rule. Nothing depends on slicer comments except the
object labels, which the firmware itself reads.

Placement:
- the header goes before the first object label (or the first Z move), after the start
  G-code;
- an after_layer block goes after the layer that prints z_top, past its retract, wipe and
  object label (nutcore.gcode.place.block_after); end_of_print goes before the end G-code;
- inserts due at the same point share a block, nearest neighbour first from where the
  toolhead is; a nut block already there comes first;
- the preheat goes preheat_lead seconds before its block by Orca's M73 R estimates, or
  preheat_layers layers before when the file has none.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

import numpy as np

from nutcore.gcode.parser import Parsed, parse
from nutcore.gcode.place import block_after, first_object_start, object_label_at
from nutcore.gcode.proof import PROOF_INSET, PROOF_RING, Z_EPS
from nutcore.report import ERROR, Finding, finding

from . import emit, profile, routine

HEADER_MARK = "; HEATSET profile"
SUCCESS, SKIPPED, FAILURE = "success", "skipped", "failure"

_M73 = re.compile(r"(?:N\d+\s*)?M73\b[^;]*?\bR\s*(\d+(?:\.\d*)?)", re.IGNORECASE)
_TEMP = re.compile(r"(?:N\d+\s*)?(M104|M109|G10|M568)(?![\d.])", re.IGNORECASE)
_WORDS = re.compile(r"([A-Za-z])\s*(-?\d+(?:\.\d*)?(?::-?\d+(?:\.\d*)?)*)")
_Z_MOVE = re.compile(r"(?:N\d+\s*)?G0*[01](?![\d.])", re.IGNORECASE)


@dataclass(frozen=True)
class InsertSpec:
    """An insert as detection reports it (milestone 5); hand-made in tests until then."""

    label: str          # for messages, for example "HEATSET_M3x5.7 #1"
    x: float            # the hole axis, bed coordinates
    y: float
    z_top: float        # the surface it ends flush with, as modelled
    hole_d: float       # the hole's diameter
    bottom_z: float     # the hole's floor or step, or the part's underside
    object: str = ""    # the object's label, when already known


@dataclass
class Planned:
    """What the G-code says about one insert."""

    spec: InsertSpec
    findings: list = field(default_factory=list)
    z_top: float | None = None     # snapped to the top of the printed layer
    line: int | None = None        # index of the line its block goes after
    object: str = ""
    block: int | None = None       # block number, once placed

    @property
    def ok(self) -> bool:
        return not any(f.level == ERROR for f in self.findings) and self.line is not None


@dataclass
class PlaceResult:
    status: str                    # success, skipped or failure
    message: str
    text: str                      # the G-code to write; the input when nothing changed
    inserts: list                  # Planned, one per InsertSpec
    changed: bool = False
    left_out: list = field(default_factory=list)   # (label, code, message)


# --- Reading the file -----------------------------------------------------------------------

def segments_near(seg: np.ndarray, x: float, y: float, radius: float) -> np.ndarray:
    """Which segments (K, 6) pass within radius of (x, y) in XY."""
    if len(seg) == 0:
        return np.zeros(0, dtype=bool)
    p0, d = seg[:, 0:2], seg[:, 3:5] - seg[:, 0:2]
    length2 = np.einsum("ij,ij->i", d, d)
    rel = np.array([x, y]) - p0
    t = np.clip(np.einsum("ij,ij->i", rel, d) / np.where(length2 > 0, length2, 1.0), 0, 1)
    gap = rel - t[:, None] * d
    return np.einsum("ij,ij->i", gap, gap) < radius * radius


def print_temperature(parsed: Parsed, line: int) -> float | None:
    """The active print tool's target temperature at a line, from the file's own commands:
    M104 and M109 (with T or for the active tool), and RepRapFirmware's G10 P S and M568 P S.
    """
    temps: dict[int, float] = {}
    for i, text in enumerate(parsed.lines[:line + 1]):
        code = text.split(";", 1)[0].strip()
        found = _TEMP.match(code)
        if not found:
            continue
        command = found[1].upper()
        words = {k.upper(): v for k, v in _WORDS.findall(code[found.end():])}
        value = words.get("S") or (words.get("R") if command == "M109" else None)
        if value is None:
            continue                               # a bare G10 retracts; G10 L sets offsets
        temp = float(value.split(":")[0])
        letter = "P" if command in ("G10", "M568") else "T"
        tool = int(float(words[letter])) if letter in words else int(parsed.line_tool[i])
        if temp > 0:
            temps[tool] = temp
    if not temps:
        return None
    active = int(parsed.line_tool[line])
    return temps.get(active, temps.get(-1, list(temps.values())[-1]))


def _header_line(parsed: Parsed) -> int:
    """Index of the line the header goes before: the first object label, or else the first
    move that changes Z (the start of the first layer)."""
    first = first_object_start(parsed)
    if first is not None:
        return first
    pos = parsed.line_pos
    for i, text in enumerate(parsed.lines):
        if i and _Z_MOVE.match(text.split(";", 1)[0].strip()) and pos[i][2] != pos[i - 1][2]:
            return i
    return 0


def _preheat_line(parsed: Parsed, block_line: int, after: int, prof: dict) -> int:
    """Index of the line the preheat goes after, never before `after`."""
    marks = [(i, float(m[1])) for i, text in enumerate(parsed.lines[:block_line + 1])
             if (m := _M73.match(text.split(";", 1)[0].strip()))]
    if marks:
        at_block = marks[-1][1]
        lead = math.ceil(prof["preheat_lead"] / 60 - 1e-9)
        early = [i for i, r in marks if r >= at_block + lead]
        return max(early[-1], after) if early else after
    seg, lines = parsed.extruding                  # no estimates: count layers instead
    tops = np.unique(np.round(seg[lines <= block_line][:, 5], 3))
    if len(tops) <= prof["preheat_layers"]:
        return after
    target = tops[-1 - prof["preheat_layers"]]
    return max(int(lines[(np.round(seg[:, 5], 3) <= target) & (lines <= block_line)].max()),
               after)


# --- One insert -----------------------------------------------------------------------------

def plan_insert(parsed: Parsed, spec: InsertSpec, prof: dict) -> Planned:
    plan = Planned(spec)
    label, r = spec.label, spec.hole_d / 2
    seg, seg_line = parsed.extruding
    local = segments_near(seg, spec.x, spec.y, r + PROOF_RING)
    seg, seg_line = seg[local], seg_line[local]
    if len(seg) == 0:
        plan.findings.append(finding("N_NOT_ON_PLATE", f"{label}: nothing is printed around "
                                     "this hole in this file, so the insert is skipped."))
        return plan
    if np.any(np.abs(seg[:, 5] - seg[:, 2]) > Z_EPS):
        plan.findings.append(finding("E_NO_LAYERS", f"{label}: extrusion changes height inside "
                                     "a move near this hole, so there are no layers to insert "
                                     "between."))
        return plan

    keys = np.round(seg[:, 5] / Z_EPS).astype(np.int64)
    unique = np.unique(keys)
    tops = unique * Z_EPS
    bottoms = np.concatenate([[0.0], tops[:-1]])
    reach = np.flatnonzero(tops >= spec.z_top - Z_EPS)
    rim = int(reach[0]) if len(reach) else len(tops) - 1     # the layer that prints z_top
    plan.z_top = float(tops[rim])

    layer_of = np.searchsorted(unique, keys)
    if np.any(layer_of < np.maximum.accumulate(layer_of) - 1):
        plan.findings.append(_print_order(label))
        return plan

    mids = (tops + bottoms) / 2
    for i in np.flatnonzero((mids > spec.bottom_z + Z_EPS) & (np.arange(len(tops)) <= rim)):
        inside = segments_near(seg[layer_of == i], spec.x, spec.y, r - PROOF_INSET)
        if inside.any():
            plan.findings.append(finding(
                "E_POCKET_NOT_EMPTY", f"{label}: plastic is printed inside the hole in the layer "
                f"at Z {tops[i]:.3f}. The insert body is still a printing part (select it, "
                "right-click, Change type, Modifier), or there is support in the hole."))
            return plan

    all_seg, all_line = parsed.extruding
    if prof["timing"] == "end_of_print":
        plan.line = block_after(parsed, parsed.last_extruding_line)
    else:
        last = int(all_line[all_seg[:, 5] <= plan.z_top + Z_EPS].max())
        plan.line = block_after(parsed, last)
        if np.any(seg_line[layer_of > rim] <= plan.line):
            plan.findings.append(_print_order(label))       # covered before the block
            return plan

    rim_line = int(seg_line[layer_of == rim].max())
    plan.object = spec.object or object_label_at(parsed, rim_line)
    problem = keep_out_problem(prof, spec, plan.z_top, all_seg[all_line <= plan.line])
    if problem:
        plan.findings.append(finding("E_KEEP_OUT", f"{label}: {problem}"))
    return plan


def keep_out_problem(prof: dict, spec: InsertSpec, z_top: float,
                     printed: np.ndarray) -> str | None:
    """Rule 8: nothing printed before the block may stand in the tool's way. Heights are
    above z_top; with after_layer nothing above z_top is printed yet."""
    p, h = prof["pad_drop"], prof["mouth_gap"]
    mouth_press = (spec.x - prof["pad_dx"], spec.y - prof["pad_dy"])
    checks = (
        ("the heater block, mouth over the hole", (spec.x, spec.y), prof["block_r"],
         h + prof["block_clearance"]),
        ("the pad, beside the hole during the hot push",
         (spec.x + prof["pad_dx"], spec.y + prof["pad_dy"]), prof["pad_d"] / 2, h - p),
        ("the heater block, pad over the hole", mouth_press, prof["block_r"],
         p + prof["block_clearance"]),
        ("the tube tip, pad over the hole", mouth_press, prof["tube_od"] / 2, p),
    )
    for what, (cx, cy), radius, height in checks:
        tall = printed[np.maximum(printed[:, 2], printed[:, 5]) > z_top + height + Z_EPS]
        near = tall[segments_near(tall, cx, cy, radius)]
        if len(near):
            top = float(np.maximum(near[:, 2], near[:, 5]).max())
            return (f"{what} would meet plastic printed {top - z_top:.2f} mm above the surface "
                    f"within {radius:.1f} mm of X{cx:.3f} Y{cy:.3f}. Clear that side of the hole "
                    "in CAD, or insert after the layer (timing after_layer).")
    return None


def _print_order(label: str) -> Finding:
    return finding("E_PRINT_ORDER", f"{label}: the print does not go up layer by layer at this "
                   "hole. Set the print sequence to By layer.")


# --- The whole file -------------------------------------------------------------------------

def place(text: str, inserts, prof: dict, *, on_error: str = "block", version: str = "",
          filament_type: str | None = None) -> PlaceResult:
    """Write the header, preheat lines and blocks for these inserts, or say why not."""
    if HEADER_MARK in text:
        return PlaceResult(SKIPPED, "The file already has heat-set blocks.", text, [])
    if not inserts:
        return PlaceResult(SUCCESS, "No heat-set inserts.", text, [])
    parsed = parse(text)
    planned = [plan_insert(parsed, spec, prof) for spec in inserts]
    placed = [p for p in planned if p.ok]

    whole = [profile.tbd_problem(prof)]
    first = min((p.line for p in placed), default=None)
    temp, source = profile.insert_temperature(
        prof, print_temperature(parsed, first if first is not None else len(parsed.lines) - 1),
        filament_type)
    whole.append(f"no insert temperature: {source}" if temp is None
                 else profile.temperature_problem(temp))
    for problem in filter(None, whole):
        for p in planned:
            if p.line is not None:
                p.findings.append(finding("E_PROFILE", f"{p.spec.label}: {problem}."))
    placed = [p for p in planned if p.ok]

    placed.sort(key=lambda p: p.line)
    blocks = _blocks(parsed, placed, prof)
    capacity = prof["magazine_capacity"]
    if len(placed) > capacity:                       # rule 9: those past the capacity
        order = [p for block in blocks for p in block]
        problem = profile.magazine_problem(prof, len(placed))
        for p in order[capacity:]:
            p.findings.append(finding("E_MAGAZINE", f"{p.spec.label}: {problem}."))
        placed = [p for p in order if p.ok]
        blocks = _blocks(parsed, placed, prof)

    failed = [(p, next(f for f in p.findings if f.level == ERROR)) for p in planned
              if any(f.level == ERROR for f in p.findings)]
    left_out = [(p.spec.label, f.code, " ".join(f.message.split())) for p, f in failed]
    if failed and on_error == "block":
        shown = "; ".join(f.message for _, f in failed[:5])
        more = f" (and {len(failed) - 5} more)" if len(failed) > 5 else ""
        return PlaceResult(FAILURE, f"Heat-set inserts: {shown}{more}", text, planned,
                           left_out=left_out)
    if not placed and not failed:
        return PlaceResult(SUCCESS, "No heat-set inserts in this file.", text, planned)

    before: dict[int, list[str]] = {}                # lines to write before line i
    after: dict[int, list[str]] = {}                 # lines to write after line i
    head = _header_line(parsed)
    header = [f"; HEATSET skipped {p.spec.label}: {f.code} {' '.join(f.message.split())}"
              for p, f in failed]
    if placed:
        header = emit.header_lines(prof, len(placed), temp, version, source) + header
    before[head] = header
    previous = head - 1
    for number, block in enumerate(blocks, start=1):
        for p in block:
            p.block = number
        line = block[0].line
        printed = parsed.extruding[0][parsed.extruding[1] <= line]
        tallest = float(np.max(printed[:, [2, 5]])) if len(printed) else 0.0
        lines = emit.block_lines(prof, emit.Block(
            number, prof["timing"], routine.z_safe(prof, tallest),
            tuple(emit.Insert(p.object, p.spec.x, p.spec.y, p.z_top) for p in block)), temp)
        heat = _preheat_line(parsed, line, max(previous, head - 1), prof)
        target = before[head] if heat < head else after.setdefault(heat, [])
        target.append(emit.preheat_line(prof, temp))
        after.setdefault(line, []).extend(lines)
        previous = line

    out, nl = [], parsed.newline
    for i, raw in enumerate(parsed.lines):
        out += [x + nl for x in before.get(i, [])]
        if i in after and not raw.endswith(("\n", "\r")):
            raw += nl
        out.append(raw)
        out += [x + nl for x in after.get(i, [])]
    message = f"{len(placed)} heat-set insert(s) in {len(blocks)} block(s)"
    if failed:
        message += f", {len(failed)} left out"
    return PlaceResult(SUCCESS, message + ".", "".join(out), planned, changed=True,
                       left_out=left_out)


def _blocks(parsed: Parsed, placed: list, prof: dict) -> list[list]:
    """Inserts sharing a block point, each block in nearest-neighbour order from where the
    toolhead is when the block starts."""
    groups: dict[int, list] = {}
    for p in placed:
        groups.setdefault(p.line, []).append(p)
    blocks = []
    for line in sorted(groups):
        todo, order = list(groups[line]), []
        x, y = parsed.line_pos[line][0], parsed.line_pos[line][1]
        while todo:
            nearest = min(todo, key=lambda p: (p.spec.x - x) ** 2 + (p.spec.y - y) ** 2)
            todo.remove(nearest)
            order.append(nearest)
            x, y = nearest.spec.x, nearest.spec.y
        blocks.append(order)
    return blocks
