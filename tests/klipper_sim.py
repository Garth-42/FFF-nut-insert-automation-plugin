"""A small stand-in for Klipper, enough to run firmware/klipper/heatset_macros.cfg on the
G-code the plugin writes.

It models what the macros rely on, the way Klipper does it (klippy/gcode.py,
extras/gcode_macro.py, probe.py, pause_resume.py, save_variables.py, manual_stepper.py):
a macro renders with Jinja and the `{` `}` delimiters before any of its lines run; SET_GCODE_
VARIABLE and SAVE_VARIABLE take Python literals; extended parameters split with shlex and
end at # or ;; a macro may not call itself; PAUSE saves the position and RESUME moves back to
it; PROBE stops at the trip height; registering axis A twice is an error. Plus a toolchanger
(T<n>, UNSELECT_TOOL), one heater and a float whose trip height the test sets. Not Klipper.
"""

from __future__ import annotations

import ast
import configparser
import copy
import re
import shlex
from dataclasses import dataclass, field

import jinja2


class KlipperError(Exception):
    """A command error: in a print, Klipper stops the print."""


@dataclass
class Move:
    x: float
    y: float
    z: float
    a: float
    xy: bool        # X or Y changed


@dataclass
class Float:
    """The float probe. surface(x, y) is what the pad lands on there, or None."""

    pad_drop: float = 0.4
    overtravel: float = 0.0
    surface: object = None
    tripped: bool = False                         # what QUERY_PROBE reads before a probe
    resist: list = field(default_factory=list)    # QUERY_PROBE answers during a push, in turn
    pad_dx: float = 20.0
    pad_dy: float = 0.0


class Klipper:
    def __init__(self, *cfg_paths, tools=(0, 3), tool=0):
        self.env = jinja2.Environment("{%", "%}", "{", "}")
        self.macros: dict[str, tuple] = {}
        parser = configparser.RawConfigParser(strict=False, inline_comment_prefixes=(";", "#"))
        for path in cfg_paths:
            parser.read(path)
        for section in parser.sections():
            if not section.startswith("gcode_macro "):
                continue
            name = section.split(None, 1)[1].upper()
            variables = {k[len("variable_"):]: ast.literal_eval(v)
                         for k, v in parser.items(section) if k.startswith("variable_")}
            self.macros[name] = (self.env.from_string(parser.get(section, "gcode")), variables)
        self.pos = {"X": 0.0, "Y": 0.0, "Z": 30.0, "A": 0.0}
        self.absolute = True
        self.feed = 3000.0
        self.tools, self.tool = list(tools), tool
        self.heater = {"temperature": 20.0, "target": 0.0}
        self.max_target = 0.0
        self.save_vars: dict = {}
        self.excluded: list = []
        self.float = Float()
        self.last_query = False
        self.axis_a = False
        self.states: dict = {}
        self.paused = False
        self.pauses: list[str] = []
        self.messages: list[tuple[str, str]] = []
        self.moves: list[Move] = []
        self.dwell = 0.0
        self.probes = 0
        self.running: set[str] = set()

    # --- What macros see ----------------------------------------------------------------------

    def status(self) -> dict:
        axis_map = {"X": 0, "Y": 1, "Z": 2, "E": 3, **({"A": 4} if self.axis_a else {})}
        status = {f"gcode_macro {name}": copy.deepcopy(variables)
                  for name, (_, variables) in self.macros.items()}
        status.update({
            "gcode_move": {"gcode_position": {"x": self.pos["X"], "y": self.pos["Y"],
                                              "z": self.pos["Z"], "e": 0.0},
                           "axis_map": axis_map},
            "probe": {"last_query": self.last_query},
            "save_variables": {"variables": copy.deepcopy(self.save_vars)},
            "toolchanger": {"tool_number": self.tool, "tool_numbers": list(self.tools)},
            "heater_generic hs_throat": dict(self.heater),
            "exclude_object": {"excluded_objects": list(self.excluded)},
        })
        return status

    # --- Running G-code -----------------------------------------------------------------------

    def run_file(self, text: str) -> None:
        """Run a print. A pause is answered with RESUME, as soon as the line that paused ends."""
        for line in text.splitlines():
            self.run(line)
            if self.paused:
                self.resume()

    def resume(self) -> None:
        state = self.states["PAUSE_STATE"]
        self.absolute = state["absolute"]
        self._move({k: state["pos"][k] for k in "XYZ"})    # RESTORE_GCODE_STATE MOVE=1
        self.paused = False

    def run(self, line: str) -> None:
        line = line.split(";", 1)[0].strip()
        if not line:
            return
        name, _, raw = line.partition(" ")
        name = name.upper()
        if name in self.macros:
            self.call(name, self._params(raw), raw)
        elif re.fullmatch(r"[GM]\d+(\.\d+)?", name):
            self._gcode(name, raw)
        elif re.fullmatch(r"T\d+", name):
            self._select(int(name[1:]))
        else:
            getattr(self, "cmd_" + name, self._unknown(name))(self._params(raw))

    def call(self, name: str, params: dict, raw: str = "") -> None:
        if name in self.running:
            raise KlipperError(f"Macro {name} called recursively")
        template, variables = self.macros[name]

        def raise_error(message):
            raise KlipperError(message)

        context = dict(copy.deepcopy(variables), printer=self.status(), params=params,
                       rawparams=raw, action_raise_error=raise_error,
                       action_respond_info=lambda m: self.messages.append(("info", m)))
        script = template.render(context)
        self.running.add(name)
        try:
            for line in script.splitlines():
                self.run(line)
        finally:
            self.running.discard(name)

    @staticmethod
    def _params(raw: str) -> dict:
        lex = shlex.shlex(raw, posix=True)
        lex.whitespace_split = True
        lex.commenters = "#;"
        out = {}
        for arg in lex:
            key, _, value = arg.partition("=")
            out[key.upper()] = value
        return out

    @staticmethod
    def _unknown(name):
        def fail(_params):
            raise KlipperError(f"Unknown command: {name}")
        return fail

    # --- Moves --------------------------------------------------------------------------------

    def _gcode(self, name: str, raw: str) -> None:
        words = {w[0].upper(): float(w[1:]) for w in raw.split()}
        if name in ("G0", "G1"):
            target = {}
            for axis in "XYZA":                # Klipper ignores A until it is registered
                if axis in words and (axis != "A" or self.axis_a):
                    target[axis] = words[axis] if self.absolute else self.pos[axis] + words[axis]
            if "F" in words:
                self.feed = words["F"]
            self._move(target)
        elif name == "G4":
            self.dwell += words.get("P", 0.0) / 1000
        elif name == "G90":
            self.absolute = True
        elif name == "G91":
            self.absolute = False
        elif name != "M400":
            raise KlipperError(f"Unexpected G-code {name}")

    def _move(self, target: dict) -> None:
        xy = any(axis in target and abs(target[axis] - self.pos[axis]) > 1e-9 for axis in "XY")
        self.pos.update(target)
        self.moves.append(Move(self.pos["X"], self.pos["Y"], self.pos["Z"], self.pos["A"], xy))

    def _select(self, number: int) -> None:
        if number not in self.tools:
            raise KlipperError(f"Unknown command: T{number}")
        self.tool = number

    # --- Extended commands ---------------------------------------------------------------------

    def cmd_SET_GCODE_VARIABLE(self, p):
        variables = self.macros[p["MACRO"].upper()][1]
        if p["VARIABLE"] not in variables:
            raise KlipperError(f"Unknown gcode_macro variable '{p['VARIABLE']}'")
        variables[p["VARIABLE"]] = ast.literal_eval(p["VALUE"])

    def cmd_SAVE_VARIABLE(self, p):
        if p["VARIABLE"] != p["VARIABLE"].lower():
            raise KlipperError("VARIABLE must not contain upper case")
        self.save_vars[p["VARIABLE"]] = ast.literal_eval(p["VALUE"])

    def cmd_RESPOND(self, p):
        self.messages.append((p.get("TYPE", "echo").lower(), p.get("MSG", "")))

    def cmd_SET_HEATER_TEMPERATURE(self, p):
        if p["HEATER"] != "hs_throat":
            raise KlipperError(f"Unknown heater {p['HEATER']}")
        self.heater["target"] = float(p["TARGET"])
        self.max_target = max(self.max_target, self.heater["target"])
        if self.heater_follows:
            self.heater["temperature"] = self.heater["target"] or 20.0

    heater_follows = True        # the throat reaches its target at once unless a test says not

    def cmd_SET_LED(self, p):
        self.messages.append(("led", f"{p['RED']} {p['GREEN']} {p['BLUE']}"))

    def cmd_QUERY_PROBE(self, p):
        """During a push the float answers from `resist` in turn; otherwise `tripped`."""
        state = self.macros["_HS_STATE"][1]
        pushing = state["total"] > 0 and not state["done"]
        if pushing:
            self.last_query = self.float.resist.pop(0) if self.float.resist else False
        else:
            self.last_query = self.float.tripped

    def cmd_PROBE(self, p):
        """Down until the float trips: the pad face on what is under it, then overtravel."""
        if self.last_query and self.float.tripped:
            raise KlipperError("Probe triggered prior to movement")
        under = self.float.surface(self.pos["X"] + self.float.pad_dx,
                                   self.pos["Y"] + self.float.pad_dy)
        if under is None:
            raise KlipperError("No trigger on probe after full movement")
        self.probes += 1
        self._move({"Z": under + self.float.pad_drop - self.float.overtravel})

    def cmd_SAVE_GCODE_STATE(self, p):
        self.states[p.get("NAME", "default")] = {"pos": dict(self.pos), "absolute": self.absolute,
                                                 "feed": self.feed}

    def cmd_RESTORE_GCODE_STATE(self, p):
        state = self.states[p.get("NAME", "default")]
        self.absolute, self.feed = state["absolute"], state["feed"]

    def cmd_PAUSE_BASE(self, p):
        if not self.paused:
            self.cmd_SAVE_GCODE_STATE({"NAME": "PAUSE_STATE"})
            self.paused = True
            self.pauses.append(self.messages[-1][1] if self.messages else "")

    def cmd_MANUAL_STEPPER(self, p):
        if p.get("GCODE_AXIS"):
            if self.axis_a:
                raise KlipperError("Must unregister axis first")
            self.axis_a = True

    def cmd_UNSELECT_TOOL(self, p):
        self.tool = -1
