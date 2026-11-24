"""Static checks of the RepRapFirmware heat-set macros, macros/heatset/*.g.

The macros cannot run here; milestone 8 runs them on the printer, rehearse mode first.
These tests hold them to what the emitter writes, and to the RRF 3.6 rules whose breach
would only show on the printer: indentation, line length, * only inside { }, letters
M98 reserves, globals declared once.
"""

import re
from pathlib import Path

import pytest

from heatsetcore import emit, profile

MACROS = Path(__file__).parents[1] / "macros" / "heatset"
CALL = re.compile(r'^\s*M98 P"heatset/(\w+)\.g"(.*)$')
ROUTINE = ("insert_start", "probe", "z", "push", "unsheath", "retract", "press", "insert_done",
           "end")


def macros() -> dict[str, str]:
    return {p.stem: p.read_text() for p in sorted(MACROS.glob("*.g"))}


def code(line: str) -> str:
    """The line without its comment; a ; inside a string does not start one."""
    in_string = False
    for i, ch in enumerate(line):
        if ch == '"':
            in_string = not in_string
        elif ch == ";" and not in_string:
            return line[:i].rstrip()
    return line.rstrip()


def code_lines(text: str):
    """(line number, indent, code) for every line that is not blank or only a comment."""
    for number, raw in enumerate(text.splitlines(), start=1):
        stripped = code(raw)
        if stripped.strip():
            yield number, len(stripped) - len(stripped.lstrip(" ")), stripped.strip()


def letters(rest: str) -> list[str]:
    """The parameter letters of an M98 call after its P"..." word."""
    out, i = [], 0
    while i < len(rest):
        if rest[i].isspace():
            i += 1
            continue
        out.append(rest[i].upper())
        i += 1
        if i < len(rest) and rest[i] == '"':
            i += 1
            while i < len(rest):
                if rest[i] == '"' and rest[i + 1:i + 2] == '"':
                    i += 2
                elif rest[i] == '"':
                    i += 1
                    break
                else:
                    i += 1
        elif i < len(rest) and rest[i] == "{":
            depth = 0
            while i < len(rest):
                depth += {"{": 1, "}": -1}.get(rest[i], 0)
                i += 1
                if depth == 0:
                    break
        else:
            while i < len(rest) and not rest[i].isspace():
                i += 1
    return out


def reads(text: str) -> tuple[set, set]:
    """(letters a macro reads, letters it only reads after checking they exist)."""
    used = set(re.findall(r"param\.([A-Z])\b", text))
    optional = set(re.findall(r"exists\(param\.([A-Z])\)", text))
    return used, optional


def emitted(mode="normal", rest_recess=0.0) -> list[str]:
    """Every M98 line the emitter writes for a print with two inserts."""
    p = {**profile.default_profile(), "tbd": [], "mode": mode, "rest_recess": rest_recess}
    block = emit.Block(1, "after_layer", 17.4, (emit.Insert("bracket_1", 120.0, 80.0, 12.4),
                                                emit.Insert('a "b"', 130.0, 80.0, 12.4)))
    lines = (emit.header_lines(p, 2, 245.0, "test") + [emit.preheat_line(p, 245.0)]
             + emit.block_lines(p, block, 245.0))
    return [x for x in lines if CALL.match(x)]


def test_every_call_the_emitter_writes_has_its_macro():
    names = {CALL.match(x)[1] for mode in ("normal", "rehearse") for x in emitted(mode)}
    assert names == {"config", "require", "preheat", "begin", "insert_start", "probe", "z",
                     "push", "unsheath", "retract", "press", "insert_done", "end"}
    assert names <= set(macros())


def test_each_macro_reads_the_letters_the_emitter_passes():
    files = macros()
    for line in emitted():
        name, rest = CALL.match(line).groups()
        passed = letters(rest)
        used, _ = reads(files[name])
        assert len(passed) == len(set(passed)), line
        assert set(passed) == used, (name, passed, used)


def test_letters_avoid_those_gcode_and_m98_reserve():
    """The spec's G, M, N, T, P, plus R (M98's own) and A (the follower axis)."""
    for line in emitted():
        assert not set(letters(CALL.match(line)[2])) & set("GMNTPRA"), line
    for name, text in macros().items():
        assert not set(reads(text)[0]) & set("GMNTPRA"), name


def test_calls_between_macros_match_what_the_callee_reads():
    files = macros()
    for name, text in files.items():
        for number, _, line in code_lines(text):
            found = CALL.match(line)
            if not found:
                continue
            callee, rest = found.groups()
            assert callee in files or callee == "count", f"{name}.g:{number} calls {callee}.g"
            if callee == "count":
                continue                        # written by save.g on the printer
            used, optional = reads(files[callee])
            passed = set(letters(rest))
            assert used - optional <= passed <= used, f"{name}.g:{number}: {passed} {used}"


def test_globals_are_declared_once_in_init():
    files = macros()
    declared = re.findall(r"^\s*global (\w+) =", files["init"], re.MULTILINE)
    assert len(declared) == len(set(declared))
    for name, text in files.items():
        if name != "init":
            assert not re.search(r"^\s*global ", text, re.MULTILINE), name
        for used in re.findall(r"global\.(\w+)", text):
            assert used in declared, f"{name}.g uses global.{used}, which init.g never declares"


def test_limits_hold_the_spec_values():
    values = dict(re.findall(r"^set global\.(\w+) = ([\d.]+)", macros()["limits"], re.MULTILINE))
    assert {k: float(v) for k, v in values.items() if k.startswith("hs_max_")} == {
        "hs_max_temp": 290.0, "hs_max_push": 8.0, "hs_max_unsheath": 2.0, "hs_max_wait": 10.0,
        "hs_max_speed": 5.0}
    assert {"hs_temp_settle", "hs_probe", "hs_lift_feed"} <= set(values)


@pytest.mark.parametrize("name", sorted(p.stem for p in MACROS.glob("*.g")))
def test_rrf_rules(name):
    text = (MACROS / f"{name}.g").read_text()
    assert "\t" not in text and "\r" not in text
    assert text.isascii(), "keep the macros ASCII"
    lines = list(code_lines(text))
    for i, (number, indent, line) in enumerate(lines):
        where = f"{name}.g:{number}"
        assert indent % 2 == 0, where
        assert len(line) + indent < 250, where                 # RRF's line and expression limit
        if re.match(r"(if|elif|while)\b|else$", line):
            assert i + 1 < len(lines) and lines[i + 1][1] > indent, f"{where}: empty block"
        depth = 0
        for ch in re.sub(r'"(?:[^"]|"")*"', '""', line):         # strings cannot hold a *
            depth += {"{": 1, "}": -1}.get(ch, 0)
            assert ch != "*" or depth > 0, f"{where}: * outside {{ }} starts a checksum"
        assert depth == 0, f"{where}: unbalanced braces"
        for literal in re.findall(r'"((?:[^"]|"")*)"', line):
            assert len(literal) < 200, where


@pytest.mark.parametrize("name", ROUTINE)
def test_routine_macros_run_only_inside_a_block_and_honour_skip(name):
    lines = [line for _, _, line in code_lines((MACROS / f"{name}.g").read_text())]
    assert lines[0] == "if !global.hs_in_block" and lines[1].startswith("abort ")
    if name not in ("insert_start", "insert_done", "end"):
        assert lines[2].startswith("if global.hs_skip") and lines[3] == "M99"


def rehearse_branch(name: str) -> tuple[list, int, int]:
    """The macro's code lines, and the first and last line of its rehearse branch."""
    lines = list(code_lines((MACROS / f"{name}.g").read_text()))
    start = next(i for i, (_, _, x) in enumerate(lines) if 'global.hs_mode != "normal"' in x)
    end = start + 1
    while end + 1 < len(lines) and lines[end + 1][1] > lines[start][1]:
        end += 1
    return [x for _, _, x in lines], start, end


@pytest.mark.parametrize("name", ["probe", "press", "push"])
def test_rehearse_mode_never_probes(name):
    """Rehearse: nothing touches the part, so the branch returns before any G38 move."""
    lines, start, end = rehearse_branch(name)
    assert lines[end] == "M99"
    probes = [i for i, x in enumerate(lines) if x.startswith("G38")]
    assert probes and min(probes) > end


@pytest.mark.parametrize("name", ["push", "retract", "unsheath"])
def test_rehearse_mode_never_moves_the_follower(name):
    lines = [line for _, _, line in code_lines((MACROS / f"{name}.g").read_text())]
    rehearse = next(i for i, x in enumerate(lines) if 'global.hs_mode != "normal"' in x)
    leave = next(i for i in range(rehearse, len(lines)) if lines[i] == "M99")
    follower = [i for i, x in enumerate(lines) if re.search(r"\bA\{", x)]
    assert follower and min(follower) > leave
    assert not any(re.search(r"\bA\{", x) for x in lines[rehearse:leave + 1])


def test_rehearse_mode_never_heats():
    files = macros()
    preheat = [line for _, _, line in code_lines(files["preheat"])]
    assert preheat.index('if global.hs_mode != "normal" || global.hs_print_skip') < next(
        i for i, x in enumerate(preheat) if x.startswith("M568"))
    begin = [line for _, _, line in code_lines(files["begin"])]
    select = begin.index("T T{global.hs_tool}")
    assert begin[select - 2:select] == ["else", "M568 P{global.hs_tool} R0 S0"]
    assert begin[select + 1:select + 3] == ['if global.hs_mode != "normal"',
                                            "M568 P{global.hs_tool} A0"]


def test_the_magazine_file_sets_what_init_reads_back():
    save = macros()["save"]
    for name in ("hs_count", "hs_loaded_key", "hs_pending_retract"):
        assert f'"set global.{name} = ' in save
    assert 'fileexists("0:/sys/heatset/count.g")' in macros()["init"]


def test_the_readme_lists_every_macro():
    readme = (MACROS / "README.md").read_text()
    for name in macros():
        assert f"`{name}.g`" in readme, name
