"""The test models, models/heatset_*.3mf: up to date with tests/models3mf.py, every mesh
closed with its faces outward, and each coupon giving its findings when the files are read
back the way Orca loads them (insert bodies set to Modifier, as the user does)."""

import zipfile
from collections import Counter
from pathlib import Path

import numpy as np
import pytest

from heatsetcore.detect import detect_inserts
from models3mf import FILES, read_3mf, write_3mf
from nutcore import library

MODELS = Path(__file__).parents[1] / "models"


def measured() -> library.Library:
    config = library.default_config()
    config["heatset"]["profiles"][0]["tbd"] = []
    return library.parse(config)


def members(path: Path) -> dict[str, bytes]:
    """What a 3MF holds, uncompressed: zlib builds compress the same bytes differently."""
    with zipfile.ZipFile(path) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


@pytest.mark.parametrize("name", FILES)
def test_the_models_are_up_to_date(name, tmp_path):
    write_3mf(tmp_path / name, FILES[name])
    assert members(tmp_path / name) == members(MODELS / name), (
        "run: uv run python tests/models3mf.py")


@pytest.mark.parametrize("name", FILES)
def test_every_mesh_is_closed_and_faces_out(name):
    snapshot, _ = read_3mf(MODELS / name)
    for obj in snapshot.objects:
        for part in obj.parts:
            t = part.triangles
            edges = Counter((int(a), int(b)) for tri in t
                            for a, b in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])))
            assert all(n == 1 for n in edges.values()), part.name      # no edge used twice
            assert all((b, a) in edges for a, b in edges), part.name    # no open edge
            c = part.vertices[t]
            volume = np.einsum("ij,ij->i", c[:, 0], np.cross(c[:, 1], c[:, 2])).sum() / 6
            assert volume > 0, part.name                                # faces outward


@pytest.mark.parametrize("name", FILES)
def test_each_coupon_gives_its_findings(name):
    snapshot, names = read_3mf(MODELS / name)
    records = detect_inserts(snapshot, measured())
    found = {names[r.object - 1]: [f.code for f in r.findings] for r in records}
    assert found == {c.name: c.expected for c in FILES[name]}


def test_the_bring_up_coupon_is_ready_for_an_insert():
    snapshot, _ = read_3mf(MODELS / "heatset_bringup_coupon.3mf")
    (record,) = detect_inserts(snapshot, measured())
    assert (record.status, record.cls) == ("ok", "UPRIGHT")
    assert record.placement == pytest.approx([150.0, 150.0, 8.0 - 2.85], abs=1e-6)
    assert record.pocket["depth"] == pytest.approx(6.7, abs=1e-6)
