"""The export step: prove each pocket in the G-code and write the insert blocks."""

from __future__ import annotations

import copy
from dataclasses import dataclass

from ..frame import PLACEABLE
from ..library import Library
from ..report import ERROR, Report, finding
from . import templates
from .parser import parse
from .proof import plan_pocket

BEGIN = ";NUT_INSERT_BEGIN"
END = ";NUT_INSERT_END"
HEADER_END = "; HEADER_BLOCK_END"
SUCCESS, SKIPPED, FAILURE = "success", "skipped", "failure"


@dataclass
class InjectResult:
    status: str      # success, skipped or failure
    message: str
    text: str        # the G-code to write; the input text when nothing changed
    report: Report   # a copy of the report with `export` and the export findings filled in
    changed: bool = False   # True when `text` differs from the input and should be written


def inject(text: str, report: Report, lib: Library, flavor: str | None = None,
           print_sequence: str | None = None) -> InjectResult:
    """Return the G-code with one insert block per nut, or say why not.

    flavor is Orca's G-code flavor, used when the firmware setting is auto.
    print_sequence is Orca's print order setting; "by object" is refused.
    """
    if BEGIN in text:
        return InjectResult(SKIPPED, "The file already has nut insert blocks.", text, report)
    out = copy.deepcopy(report)
    if report.stale:
        message = ("E_STALE: the model changed after the last nut check. Run Check nuts, "
                   "then slice and export again.")
        return InjectResult(FAILURE, message, text, out)
    if not out.nuts:
        return InjectResult(SUCCESS, "No nuts in the report.", text, out)

    settings = lib.settings
    parsed = parse(text)
    by_object = "object" in str(print_sequence or "").lower()
    firmware = "unknown"
    planned = []    # (record, plan, rendered lines)
    failed = []     # (record, finding) for nuts that cannot be inserted because of an error
    passed = []     # records left out without an error: tilted, rolled

    for record in out.nuts:
        record.export = None
        nut = lib.get(record.key)
        measured = (record.cls in PLACEABLE and nut is not None and record.box is not None
                    and record.z_low is not None
                    and (record.roof_z is not None or record.rim_z is not None))
        if not measured:
            errors = [f for f in record.findings if f.level == ERROR]
            if errors:
                failed.append((record, errors[0]))
            else:
                passed.append(record)
            continue

        plan = plan_pocket(parsed, record, settings.min_top_clearance_mm, nut.tool_reach)
        if not plan.on_plate:
            record.findings += plan.findings
            record.export = {"skipped": "N_NOT_ON_PLATE"}
            continue
        check_errors = [f for f in record.findings if f.level == ERROR]
        if by_object and not plan.has_error():
            plan.findings.append(finding(
                "E_PRINT_ORDER", f"{record.label}: the print sequence is by object. Nut "
                "insertion needs By layer."))
        lines = None
        if not check_errors and not plan.has_error():
            try:
                firmware = templates.pick_firmware(settings.firmware, flavor)
                template = templates.firmware_template(settings.templates, firmware)
                line = plan.line
                rx, ry, rz = parsed.line_pos[line]
                lines = templates.render(template, {
                    "index": str(record.index), "key": record.key, "cls": record.cls,
                    "x": templates.fmt_length(record.placement[0]),
                    "y": templates.fmt_length(record.placement[1]),
                    "z": templates.fmt_length(plan.z),
                    "z_low": templates.fmt_length(plan.z_low),
                    "z_high": templates.fmt_length(plan.z_high),
                    "yaw": templates.fmt_angle(record.yaw_deg),
                    "feeder": str(nut.feeder),
                    "layer_z": templates.fmt_length(plan.layer_z),
                    "tool": str(int(parsed.line_tool[line])),
                    "rx": templates.fmt_length(rx), "ry": templates.fmt_length(ry),
                    "rz": templates.fmt_length(rz)})
            except templates.TemplateError as exc:
                plan.findings.append(finding("E_TEMPLATE", f"{record.label}: {exc}."))
        record.findings += plan.findings
        errors = check_errors + [f for f in plan.findings if f.level == ERROR]
        if errors:
            failed.append((record, errors[0]))
            continue
        record.export = {"layer": plan.layer, "layer_z": plan.layer_z, "z": plan.z,
                         "z_low": plan.z_low, "z_high": plan.z_high,
                         "after_line": plan.line + 1}
        planned.append((record, plan, lines))

    if failed and settings.on_error == "block":
        shown = "; ".join(f.message for _, f in failed[:5])
        more = f" (and {len(failed) - 5} more)" if len(failed) > 5 else ""
        return InjectResult(FAILURE, f"Nut insert: {shown}{more}", text, out)
    if not planned and not failed:
        return InjectResult(SUCCESS, "No nuts to insert in this file.", text, out)

    nl = parsed.newline
    summary = [f"; NUT_INSERT_SUMMARY firmware={firmware} inserted={len(planned)} "
               f"skipped={len(failed) + len(passed)}"]
    for record, plan, _ in planned:
        x, y = record.placement[0], record.placement[1]
        summary.append(f"; nut {record.index} {record.name} {record.cls} X{x:.3f} Y{y:.3f} "
                       f"Z{plan.z:.3f} after layer_z={plan.layer_z:.3f}")
    for record, problem in failed:
        message = " ".join(problem.message.split())
        summary.append(f"; nut {record.index} {record.name} skipped: {problem.code} {message}")
    for record in passed:
        summary.append(f"; nut {record.index} {record.name} skipped: {record.cls or 'no data'}")

    blocks: dict[int, list] = {}
    for item in planned:
        blocks.setdefault(item[1].line, []).append(item)
    header_at = next((i for i, line in enumerate(parsed.lines)
                      if line.strip() == HEADER_END), None)

    result: list[str] = []
    if header_at is None:
        result += [line + nl for line in summary]
    for i, line in enumerate(parsed.lines):
        if not line.endswith(("\n", "\r")) and (i in blocks or i == header_at):
            line += nl
        result.append(line)
        if i == header_at:
            result += [text_line + nl for text_line in summary]
        if i in blocks:
            group = blocks[i]
            layer_z = max(plan.layer_z for _, plan, _ in group)
            result.append(f"{BEGIN} layer_z={layer_z:.3f} count={len(group)}{nl}")
            for _, _, lines in group:
                result += [text_line + nl for text_line in lines]
            result.append(END + nl)

    message = f"{len(planned)} nut insert block(s) written"
    if failed or passed:
        message += f", {len(failed) + len(passed)} nut(s) skipped"
    return InjectResult(SUCCESS, message + ".", "".join(result), out, changed=True)
