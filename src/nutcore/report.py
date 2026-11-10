"""The report: one record per nut, as objects, JSON and CSV."""

from __future__ import annotations

import csv
import io
import json
from dataclasses import asdict, dataclass, field

SCHEMA = 1
ERROR, WARNING, NOTE = "error", "warning", "note"


@dataclass(frozen=True)
class Finding:
    code: str      # stable string such as E_WIDTH
    level: str     # error, warning or note
    message: str


def level_of(code: str) -> str:
    return {"E": ERROR, "W": WARNING, "N": NOTE}[code[0]]


def finding(code: str, message: str) -> Finding:
    return Finding(code, level_of(code), message)


@dataclass
class NutRecord:
    index: int                    # nut number in the report, from 1
    object: int                   # object, copy and part numbers, from 1
    instance: int
    part: int
    name: str
    key: str | None = None
    cls: str | None = None
    axis: list | None = None
    yaw_deg: float | None = None
    tilt_deg: float | None = None
    roll_deg: float | None = None
    body_size: list | None = None
    modelled_centre: list | None = None
    placement: list | None = None
    z_low: float | None = None
    z_high: float | None = None
    roof_z: float | None = None
    rim_z: float | None = None
    pocket: dict | None = None    # width, thickness, depth, seat_gaps
    box: dict | None = None       # centre, axes, half: what the preview draws
    window: list | None = None    # insert window [z_from, z_to]; z_to is None for open-top
    status: str = "ok"
    findings: list[Finding] = field(default_factory=list)
    export: dict | None = None    # filled by the export step

    @property
    def label(self) -> str:
        return f"{self.name} #{self.index}"

    def add(self, code: str, message: str) -> None:
        self.findings.append(finding(code, message))
        self.status = status_of(self.findings)

    def has_error(self) -> bool:
        return any(f.level == ERROR for f in self.findings)


def status_of(findings) -> str:
    levels = {f.level for f in findings}
    if ERROR in levels:
        return "error"
    if WARNING in levels:
        return "warning"
    return "ok"


def _clean(value):
    """Round floats so the JSON reads 5.8, not 5.800000000000001."""
    if isinstance(value, float):
        return round(value, 6) + 0.0
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    return value


@dataclass
class Report:
    fingerprint: str = ""
    stale: bool = False
    nuts: list[NutRecord] = field(default_factory=list)

    @property
    def summary(self) -> dict:
        counts = {"ok": 0, "warning": 0, "error": 0}
        for nut in self.nuts:
            counts[nut.status] += 1
        return counts

    def to_dict(self) -> dict:
        return {"schema": SCHEMA, "fingerprint": self.fingerprint, "stale": self.stale,
                "summary": self.summary, "nuts": [_clean(asdict(nut)) for nut in self.nuts]}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, data: dict) -> Report:
        if data.get("schema") != SCHEMA:
            raise ValueError(f"report schema must be {SCHEMA}")
        nuts = []
        for item in data.get("nuts", []):
            item = dict(item)
            item["findings"] = [Finding(**f) for f in item.get("findings", [])]
            nuts.append(NutRecord(**item))
        return cls(fingerprint=data.get("fingerprint", ""), stale=bool(data.get("stale")),
                   nuts=nuts)

    @classmethod
    def from_json(cls, text: str) -> Report:
        return cls.from_dict(json.loads(text))

    def to_csv(self) -> str:
        out = io.StringIO()
        writer = csv.writer(out, lineterminator="\n")
        writer.writerow(["index", "name", "key", "object", "instance", "class", "angle_deg",
                         "x", "y", "z", "z_low", "z_high", "roof_z", "rim_z", "pocket_width",
                         "pocket_thickness", "pocket_depth", "status", "findings"])

        def num(value, digits=3):
            return "" if value is None else f"{value:.{digits}f}"

        for n in self.nuts:
            pocket = n.pocket or {}
            angle = n.yaw_deg if n.cls in ("FLAT", "EDGE", "CORNER") else (
                n.roll_deg if n.cls == "ROLLED" else n.tilt_deg)
            x, y, z = n.placement or (None, None, None)
            writer.writerow([
                n.index, n.name, n.key or "", n.object, n.instance, n.cls or "", num(angle, 2),
                num(x), num(y), num(z), num(n.z_low), num(n.z_high), num(n.roof_z),
                num(n.rim_z), " x ".join(num(w) for w in pocket.get("width") or []),
                num(pocket.get("thickness")), num(pocket.get("depth")), n.status,
                " | ".join(f"{f.code}: {f.message}" for f in n.findings)])
        return out.getvalue()
