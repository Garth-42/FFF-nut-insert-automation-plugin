"""A small stand-in for RepRapFirmware 3.6, enough to run macros/heatset/*.g on the G-code
the plugin writes.

It follows the Duet3D documentation of the meta commands and the G-codes the macros use:
blocks by indentation, `var` scoped to its block, `global` declared once, `set`, `if`,
`elif`, `else`, `while` with `iterations`, `break` and `continue`, `abort` ending the
print, `echo` to the console or a file; expressions with RRF's precedence (`&&` and `||`
bind alike, `^` below them), `#` length, `exists()`, `fileexists()`; M98 with parameters,
M99, G0/G1 within the axis limits, G4, G90/G91, G38.3 on Z or A, M400, M568,
T T{n} and T-1, M291 message boxes answered from a script. The float probe, the throat
heater and the part under the pad are models the test sets. Not RepRapFirmware: anything
else is an error here, so a macro that strays past this subset fails its test.

Where the documentation leaves RRF's behaviour open, the stand-in takes the stricter side:
`&&` and `||` evaluate both operands (so a guard like `exists(x) && x > 1` fails here), and
a macro's G90/G91 and feed rate carry on after it returns (so a macro must restore them).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

SYS = "0:/sys/"


class RRFError(Exception):
    """An error RepRapFirmware would report."""


class RRFAbort(Exception):
    """`abort`: the print ends."""


class _Return(Exception):
    pass


class _Break(Exception):
    pass


class _Continue(Exception):
    pass


# --- Expressions ----------------------------------------------------------------------------

_TOKEN = re.compile(r"""
    \s*(?:
      (?P<num>0x[0-9a-fA-F]+|\d+\.\d*|\.\d+|\d+(?:[eE][-+]?\d+)?)
    | (?P<str>"(?:[^"]|"")*")
    | (?P<chr>'.')
    | (?P<name>[A-Za-z_][A-Za-z0-9_]*)
    | (?P<op>==|!=|<=|>=|&&|\|\||[-+*/^!#<>=&|?:()\[\]{},.])
    )""", re.VERBOSE)

_BINARY = {"^": 2, "&": 3, "&&": 3, "|": 3, "||": 3, "=": 4, "==": 4, "!=": 4, "<": 4,
           "<=": 4, ">": 4, ">=": 4, "+": 5, "-": 5, "*": 6, "/": 6}


def tokens(text: str) -> list[tuple[str, object]]:
    out, pos = [], 0
    while pos < len(text):
        if text[pos:].strip() == "":
            break
        found = _TOKEN.match(text, pos)
        if not found or found.end() == pos:
            raise RRFError(f"cannot read the expression at {text[pos:]!r}")
        pos = found.end()
        kind = found.lastgroup
        value = found[kind]
        if kind == "num":
            value = (int(value, 16) if value.lower().startswith("0x") else
                     float(value) if any(c in value for c in ".eE") else int(value))
        elif kind == "str":
            value = value[1:-1].replace('""', '"')
        elif kind == "chr":
            kind, value = "str", value[1]
        out.append((kind, value))
    return out


class _Parser:
    """Expression text to a small tree: ("num", v), ("str", s), ("name", n),
    ("member", obj, n), ("index", obj, i), ("call", n, args), ("unary", op, x),
    ("binary", op, a, b), ("ternary", c, a, b), ("array", items)."""

    def __init__(self, text: str):
        self.toks, self.i = tokens(text), 0

    def peek(self):
        return self.toks[self.i] if self.i < len(self.toks) else (None, None)

    def take(self, value=None):
        kind, got = self.peek()
        if kind is None or (value is not None and got != value):
            raise RRFError(f"expected {value!r}, found {got!r}")
        self.i += 1
        return kind, got

    def done(self) -> bool:
        return self.i >= len(self.toks)

    def expression(self):
        cond = self.binary(1)
        if self.peek() == ("op", "?"):
            self.take("?")
            a = self.expression()
            self.take(":")
            b = self.expression()
            return ("ternary", cond, a, b)
        return cond

    def binary(self, level):
        left = self.unary()
        while True:
            kind, op = self.peek()
            if kind != "op" or op not in _BINARY or _BINARY[op] < level:
                return left
            self.take()
            right = self.binary(_BINARY[op] + 1)
            left = ("binary", op, left, right)

    def unary(self):
        kind, op = self.peek()
        if kind == "op" and op in ("!", "-", "+", "#"):
            self.take()
            return ("unary", op, self.unary())
        return self.postfix(self.primary())

    def postfix(self, node):
        while True:
            kind, op = self.peek()
            if (kind, op) == ("op", "."):
                self.take()
                _, name = self.take()
                node = ("member", node, name)
            elif (kind, op) == ("op", "["):
                self.take()
                index = self.expression()
                self.take("]")
                node = ("index", node, index)
            elif (kind, op) == ("op", "(") and node[0] == "name":
                self.take()
                args = []
                while self.peek() != ("op", ")"):
                    args.append(self.expression())
                    if self.peek() == ("op", ","):
                        self.take()
                self.take(")")
                node = ("call", node[1], args)
            else:
                return node

    def primary(self):
        kind, value = self.take()
        if kind in ("num", "str"):
            return (kind, value)
        if kind == "name":
            return ("name", value)
        if value == "(":
            node = self.expression()
            self.take(")")
            return node
        if value == "{":
            items = [self.expression()]
            comma = False
            while self.peek() == ("op", ","):
                self.take()
                comma = True
                if self.peek() == ("op", "}"):
                    break
                items.append(self.expression())
            self.take("}")
            return ("array", items) if comma else items[0]
        raise RRFError(f"unexpected {value!r} in an expression")


def parse_expression(text: str):
    parser = _Parser(text)
    node = parser.expression()
    if not parser.done():
        raise RRFError(f"unexpected {parser.peek()[1]!r} after an expression in {text!r}")
    return node


def text_of(value) -> str:
    """How `^` and echo turn a value into text."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:.3f}".rstrip("0").rstrip(".") if value != int(value) else f"{value:.1f}"
    if value is None:
        return "null"
    if isinstance(value, list):
        return "{" + ",".join(text_of(v) for v in value) + "}"
    return str(value)


# --- The machine ----------------------------------------------------------------------------

@dataclass
class Move:
    x: float
    y: float
    z: float
    a: float
    xy: bool


@dataclass
class Float:
    """The float: what the pad lands on, and how the insert resists the push."""

    pad_drop: float = 0.4
    overtravel: float = 0.0
    pad_dx: float = 20.0
    pad_dy: float = 0.0
    surface: object = None          # f(x, y, n): height the pad lands on, n = Z probes so far
    stuck: bool = False             # reads tripped whatever happens
    resist_at: float | None = None  # A position at which the insert starts to resist
    soften_waits: int = 0           # waits (G4) after which it gives way
    tripped: bool = False


@dataclass
class Frame:
    params: dict
    scopes: list = field(default_factory=lambda: [{}])
    loops: list = field(default_factory=list)


class RRF:
    def __init__(self, macro_dir, print_tool=0, heatset_tool=3):
        self.fs: dict[str, str] = {}
        for path in sorted(macro_dir.glob("*.g")):
            self.fs[SYS + "heatset/" + path.name] = path.read_text()
        self.axes = [{"letter": c, "min": lo, "max": hi, "homed": True}
                     for c, lo, hi in (("X", 0.0, 300.0), ("Y", 0.0, 300.0), ("Z", 0.0, 250.0),
                                       ("A", 0.0, 200.0))]
        self.pos = {"X": 0.0, "Y": 0.0, "Z": 30.0, "A": 0.0}
        self.absolute = True
        self.feed = 3000.0
        self.heaters = {0: self._heater(), 1: self._heater(), 2: self._heater()}
        self.tools = {print_tool: {"heaters": [1], "active": 0.0, "standby": 0.0},
                      heatset_tool: {"heaters": [2], "active": 0.0, "standby": 0.0}}
        self.current_tool = print_tool
        self.heater_follows = True
        self.globals: dict = {}
        self.float = Float()
        self.objects = None
        self.answers: list = []
        self.dialogs: list[tuple] = []
        self.messages: list[str] = []
        self.moves: list[Move] = []
        self.dwell = 0.0
        self.z_probes = 0
        self.input = None
        self.result = 0
        self.aborted: str | None = None
        self.max_target = {h: 0.0 for h in self.heaters}
        self.on_dwell = None
        self.tool_changes: list[int] = []
        self._trees: dict = {}

    @staticmethod
    def _heater():
        return {"current": 20.0, "active": 0.0, "standby": 0.0, "state": "off"}

    # --- Object model -------------------------------------------------------------------------

    def om(self, name: str):
        if name == "move":
            axes = [dict(a, userPosition=self.pos[a["letter"]]) for a in self.axes]
            return {"axes": axes}
        if name == "sensors":
            value = 1000 if (self.float.stuck or self.float.tripped) else 0
            return {"probes": [{"value": [0], "threshold": 500},
                               {"value": [value], "threshold": 500}]}
        if name == "tools":
            top = max(self.tools)
            return [({"number": n, "heaters": list(self.tools[n]["heaters"])}
                     if n in self.tools else None) for n in range(top + 1)]
        if name == "heat":
            return {"heaters": [dict(self.heaters[h]) for h in sorted(self.heaters)]}
        if name == "state":
            return {"currentTool": self.current_tool}
        if name == "job":
            return {"build": None if self.objects is None else
                    {"objects": [dict(o) for o in self.objects], "currentObject": -1}}
        raise RRFError(f"unknown value '{name}'")

    # --- Evaluating ---------------------------------------------------------------------------

    def eval(self, node, frame: Frame):
        kind = node[0]
        if kind in ("num", "str"):
            return node[1]
        if kind == "array":
            return [self.eval(n, frame) for n in node[1]]
        if kind == "name":
            return self._name(node[1], frame)
        if kind == "member":
            base = node[1]
            if base[0] == "name" and base[1] in ("param", "var", "global"):
                return self._variable(base[1], node[2], frame)
            obj = self.eval(base, frame)
            if obj is None:
                raise RRFError(f"cannot take '{node[2]}' of null")     # RRF 3.6 reports it
            if not isinstance(obj, dict) or node[2] not in obj:
                raise RRFError(f"unknown value '{node[2]}'")
            return obj[node[2]]
        if kind == "index":
            obj, index = self.eval(node[1], frame), self.eval(node[2], frame)
            if not isinstance(obj, (list, str)) or not isinstance(index, int) or not (
                    0 <= index < len(obj)):
                raise RRFError("array index out of bounds")
            return obj[index]                        # an undefined tool reads as null
        if kind == "call":
            return self._call(node[1], node[2], frame)
        if kind == "unary":
            op, value = node[1], self.eval(node[2], frame)
            if op == "!":
                return not self._bool(value)
            if op == "#":
                return len(value)
            return -value if op == "-" else +value
        if kind == "ternary":
            return self.eval(node[2] if self._bool(self.eval(node[1], frame)) else node[3], frame)
        op, a = node[1], node[2]
        x, y = self.eval(a, frame), self.eval(node[3], frame)      # both sides, always
        if op in ("&&", "&"):
            return self._bool(x) and self._bool(y)
        if op in ("||", "|"):
            return self._bool(x) or self._bool(y)
        if op == "^":
            return text_of(x) + text_of(y)
        if op in ("=", "=="):
            return x == y
        if op == "!=":
            return x != y
        if op in ("<", "<=", ">", ">="):
            if not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in (x, y)):
                raise RRFError(f"cannot compare {x!r} and {y!r}")
            return {"<": x < y, "<=": x <= y, ">": x > y, ">=": x >= y}[op]
        if not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in (x, y)):
            raise RRFError(f"cannot apply {op} to {x!r} and {y!r}")
        if op == "+":
            return x + y
        if op == "-":
            return x - y
        if op == "*":
            return x * y
        return x / y

    @staticmethod
    def _bool(value) -> bool:
        if not isinstance(value, bool):
            raise RRFError(f"expected a boolean, found {value!r}")
        return value

    def _name(self, name: str, frame: Frame):
        constants = {"true": True, "false": False, "null": None, "pi": math.pi}
        if name in constants:
            return constants[name]
        if name == "iterations":
            if not frame.loops:
                raise RRFError("'iterations' used outside a loop")
            return frame.loops[-1]
        if name == "input":
            return self.input
        if name == "result":
            return self.result
        return self.om(name)

    def _variable(self, space: str, name: str, frame: Frame):
        if space == "param":
            if name not in frame.params:
                raise RRFError(f"unknown value 'param.{name}'")
            return frame.params[name]
        if space == "var":
            for scope in reversed(frame.scopes):
                if name in scope:
                    return scope[name]
            raise RRFError(f"unknown variable 'var.{name}'")
        if name not in self.globals:
            raise RRFError(f"unknown variable 'global.{name}'")
        return self.globals[name]

    def _call(self, name: str, args, frame: Frame):
        if name == "exists":
            try:
                return self.eval(args[0], frame) is not None
            except RRFError:
                return False
        values = [self.eval(a, frame) for a in args]
        if name == "fileexists":
            return self._path(values[0]) in self.fs
        if name == "abs":
            return abs(values[0])
        if name == "min":
            return min(values)
        if name == "max":
            return max(values)
        if name == "sqrt":
            return math.sqrt(values[0])
        raise RRFError(f"unknown function '{name}'")

    # --- Files and blocks ---------------------------------------------------------------------

    @staticmethod
    def _path(name: str) -> str:
        return name if name.startswith("0:/") else SYS + name.lstrip("/")

    @staticmethod
    def _code(line: str) -> str:
        """The line without its comment: ; outside strings and braces."""
        quoted, depth = False, 0
        for i, ch in enumerate(line):
            if ch == '"':
                quoted = not quoted
            elif not quoted and ch == "{":
                depth += 1
            elif not quoted and ch == "}":
                depth -= 1
            elif ch == ";" and not quoted and depth == 0:
                return line[:i].rstrip()
        return line.rstrip()

    def _tree(self, text: str) -> list:
        """Lines to nodes [indent, code, children], blocks by indentation."""
        root: list = []
        stack = [(-1, root)]
        for raw in text.splitlines():
            if "\t" in raw:
                raise RRFError("tab in a macro")
            code = self._code(raw)
            if not code.strip():
                continue
            indent = len(code) - len(code.lstrip(" "))
            while stack[-1][0] >= indent:
                stack.pop()
            node = [indent, code.strip(), []]
            stack[-1][1].append(node)
            stack.append((indent, node[2]))
        return root

    def _block(self, nodes: list, frame: Frame) -> None:
        frame.scopes.append({})
        try:
            i = 0
            while i < len(nodes):
                i = self._statement(nodes, i, frame)
        finally:
            frame.scopes.pop()

    def _statement(self, nodes: list, i: int, frame: Frame) -> int:
        _, code, children = nodes[i]
        word = code.split(None, 1)[0]
        rest = code[len(word):].strip()
        if word == "if":
            chain = [(rest, children)]
            j = i + 1
            while j < len(nodes) and nodes[j][1].split(None, 1)[0] in ("elif", "else"):
                kw = nodes[j][1].split(None, 1)[0]
                chain.append((nodes[j][1][len(kw):].strip() if kw == "elif" else None,
                              nodes[j][2]))
                j += 1
                if kw == "else":
                    break
            for cond, body in chain:
                if cond is None or self._bool(self.eval(parse_expression(cond), frame)):
                    self._block(body, frame)
                    break
            return j
        if word in ("elif", "else"):
            raise RRFError(f"'{word}' without 'if'")
        if word == "while":
            condition = parse_expression(rest)
            frame.loops.append(0)
            try:
                while self._bool(self.eval(condition, frame)):
                    try:
                        self._block(children, frame)
                    except _Break:
                        break
                    except _Continue:
                        pass
                    frame.loops[-1] += 1
                    if frame.loops[-1] > 10000:
                        raise RRFError("a loop ran 10000 times")
            finally:
                frame.loops.pop()
            return i + 1
        if word == "break":
            raise _Break
        if word == "continue":
            raise _Continue
        if word == "var":
            name, _, expr = rest.partition("=")
            name = name.strip()
            if any(name in scope for scope in frame.scopes):
                raise RRFError(f"variable '{name}' already exists")
            frame.scopes[-1][name] = self.eval(parse_expression(expr), frame)
        elif word == "global":
            name, _, expr = rest.partition("=")
            name = name.strip()
            if name in self.globals:
                raise RRFError(f"global variable '{name}' already exists")
            self.globals[name] = self.eval(parse_expression(expr), frame)
        elif word == "set":
            target, _, expr = rest.partition("=")
            space, _, name = target.strip().partition(".")
            value = self.eval(parse_expression(expr), frame)
            if space == "global":
                if name not in self.globals:
                    raise RRFError(f"unknown variable 'global.{name}'")
                self.globals[name] = value
            elif space == "var":
                for scope in reversed(frame.scopes):
                    if name in scope:
                        scope[name] = value
                        break
                else:
                    raise RRFError(f"unknown variable 'var.{name}'")
            else:
                raise RRFError(f"cannot set {target.strip()}")
        elif word == "abort":
            raise RRFAbort(text_of(self.eval(parse_expression(rest), frame)) if rest else "")
        elif word == "echo":
            self._echo(rest, frame)
        elif word != "skip":
            self.command(code, frame)
        if children and word not in ("var", "global", "set"):
            self._block(children, frame)            # a deeper line starts a block of its own
        return i + 1

    def _echo(self, rest: str, frame: Frame) -> None:
        mode = None
        found = re.match(r'(>{1,3})("(?:[^"]|"")*"|\{[^}]*\})\s*', rest)
        if found:
            mode = found[1]
            target = self.eval(parse_expression(found[2]), frame)
            rest = rest[found.end():]
        parts = []
        parser = _Parser(rest)
        while not parser.done():
            parts.append(text_of(self.eval(parser.expression(), frame)))
            if not parser.done():
                parser.take(",")
        text = " ".join(parts)
        if mode is None:
            self.messages.append(text)
            return
        path = self._path(target)
        old = self.fs.get(path, "") if mode != ">" else ""
        self.fs[path] = old + text + ("" if mode == ">>>" else "\n")

    # --- G-code ------------------------------------------------------------------------------

    def _words(self, text: str, frame: Frame) -> dict:
        """Parameter letters and their values: numbers, "strings" or {expressions}."""
        out, i = {}, 0
        while i < len(text):
            if text[i].isspace():
                i += 1
                continue
            letter = text[i].upper()
            i += 1
            if i < len(text) and text[i] == '"':
                j = i + 1
                while j < len(text):
                    if text[j] == '"' and text[j + 1:j + 2] == '"':
                        j += 2
                    elif text[j] == '"':
                        break
                    else:
                        j += 1
                out[letter] = text[i + 1:j].replace('""', '"')
                i = j + 1
            elif i < len(text) and text[i] == "{":
                depth, j, quoted = 0, i, False
                while j < len(text):
                    if text[j] == '"':
                        quoted = not quoted
                    elif not quoted:
                        depth += {"{": 1, "}": -1}.get(text[j], 0)
                        if depth == 0:
                            break
                    j += 1
                out[letter] = self.eval(parse_expression(text[i:j + 1]), frame)
                i = j + 1
            else:
                j = i
                while j < len(text) and not text[j].isspace():
                    j += 1
                token = text[i:j]
                out[letter] = (float(token) if "." in token else int(token)) if token else None
                i = j
        return out

    def command(self, code: str, frame: Frame) -> None:
        found = re.match(r"([GMT])(-?\d+(?:\.\d+)?)?\s*(.*)$", code)
        if not found:
            raise RRFError(f"cannot read {code!r}")
        letter, number, rest = found.groups()
        words = self._words(rest, frame)
        self.result = 0
        if letter == "T":
            self._select(words["T"] if number is None else int(number))
        elif (letter, number) in (("G", "0"), ("G", "1")):
            self._g1(words)
        elif (letter, number) == ("G", "4"):
            self._dwell(words.get("S", 0) + words.get("P", 0) / 1000)
        elif (letter, number) == ("G", "90"):
            self.absolute = True
        elif (letter, number) == ("G", "91"):
            self.absolute = False
        elif (letter, number) == ("G", "38.3"):
            self._probe(words)
        elif (letter, number) == ("M", "400"):
            pass
        elif (letter, number) == ("M", "98"):
            self.call(words.pop("P"), words)
        elif (letter, number) == ("M", "99"):
            raise _Return
        elif (letter, number) == ("M", "568"):
            self._m568(words)
        elif (letter, number) == ("M", "291"):
            self._m291(words)
        else:
            raise RRFError(f"command {letter}{number} is not in the stand-in")

    def call(self, name: str, params: dict) -> None:
        path = self._path(name)
        if path not in self.fs:
            raise RRFError(f"macro file {name} not found")
        if path not in self._trees or path.endswith("count.g"):
            self._trees[path] = self._tree(self.fs[path])
        frame = Frame(params=dict(params))
        try:
            self._block(self._trees[path], frame)
        except _Return:
            pass

    def run_file(self, text: str) -> None:
        """Run a print. abort ends it; the message is kept in `aborted`."""
        frame = Frame(params={})
        try:
            self._block(self._tree(text), frame)
        except RRFAbort as exc:
            self.aborted = str(exc)

    def run(self, line: str) -> None:
        """One line from the console."""
        self._block(self._tree(line), Frame(params={}))

    # --- Moves, probing, heat, tools, messages ------------------------------------------------

    def _g1(self, words: dict) -> None:
        target = {}
        for axis in "XYZA":
            if axis in words:
                value = words[axis] if self.absolute else self.pos[axis] + words[axis]
                spec = next(a for a in self.axes if a["letter"] == axis)
                if not spec["homed"]:
                    raise RRFError(f"axis {axis} is not homed")
                if not spec["min"] - 1e-9 <= value <= spec["max"] + 1e-9:
                    raise RRFError(f"G1 {axis}{value} is outside the machine limits")
                target[axis] = value
        if "F" in words:
            self.feed = words["F"]
        if "Z" in target and target["Z"] > self.pos["Z"] + 1e-9:
            self.float.tripped = False             # lifting lets the float go
        self._move(target)

    def _move(self, target: dict) -> None:
        xy = any(axis in target and abs(target[axis] - self.pos[axis]) > 1e-9 for axis in "XY")
        self.pos.update(target)
        self.moves.append(Move(self.pos["X"], self.pos["Y"], self.pos["Z"], self.pos["A"], xy))

    def _dwell(self, seconds: float) -> None:
        self.dwell += seconds
        if self.on_dwell:
            self.on_dwell(self.dwell)          # a test's hand on the machine, by the clock
        f = self.float
        if f.tripped and f.resist_at is not None:
            f.soften_waits -= 1
            if f.soften_waits <= 0:
                f.tripped, f.resist_at = False, None    # the plastic gave way

    def _probe(self, words: dict) -> None:
        f = self.float
        if words.get("K") != 1:
            raise RRFError("G38.3 on another probe")
        if f.stuck or f.tripped:
            return                                      # already in the target state
        if "F" in words:
            self.feed = words["F"]
        if "Z" in words:
            under = f.surface(self.pos["X"] + f.pad_dx, self.pos["Y"] + f.pad_dy, self.z_probes)
            self.z_probes += 1
            trip = None if under is None else under + f.pad_drop - f.overtravel
            if trip is not None and words["Z"] <= trip <= self.pos["Z"]:
                f.tripped = True
                self._move({"Z": trip})
            else:
                self._move({"Z": words["Z"]})
        elif "A" in words:
            if f.resist_at is not None and self.pos["A"] < f.resist_at < words["A"]:
                f.tripped = True
                self._move({"A": f.resist_at})
            else:
                self._move({"A": words["A"]})
        else:
            raise RRFError("G38.3 needs a target")

    def _set_heaters(self, number: int) -> None:
        tool = self.tools[number]
        for h in tool["heaters"]:
            heater = self.heaters[h]
            heater["active"], heater["standby"] = tool["active"], tool["standby"]
            target = {"active": tool["active"], "standby": tool["standby"], "off": 0.0}[
                heater["state"]]
            self.max_target[h] = max(self.max_target[h], target)
            if self.heater_follows:
                heater["current"] = target if target > 0 else 20.0

    def _m568(self, words: dict) -> None:
        number = words.get("P", self.current_tool)
        tool = self.tools[number]
        if "S" in words:
            tool["active"] = float(words["S"])
        if "R" in words:
            tool["standby"] = float(words["R"])
        if "A" in words:
            for h in tool["heaters"]:
                self.heaters[h]["state"] = {0: "off", 1: "standby", 2: "active"}[words["A"]]
        self._set_heaters(number)

    def _select(self, number: int) -> None:
        if number == self.current_tool:
            return
        if self.current_tool >= 0:
            for h in self.tools[self.current_tool]["heaters"]:
                self.heaters[h]["state"] = "standby"
            self._set_heaters(self.current_tool)
        if number >= 0:
            if number not in self.tools:
                raise RRFError(f"tool {number} is not defined")
            for h in self.tools[number]["heaters"]:
                self.heaters[h]["state"] = "active"
            self._set_heaters(number)
        self.current_tool = number
        self.tool_changes.append(number)

    def _m291(self, words: dict) -> None:
        mode = words.get("S", 1)
        if len(str(words.get("P", ""))) >= 250:
            raise RRFError("M291 message over RRF's limit")
        self.dialogs.append((mode, words.get("R", ""), words.get("P", "")))
        if mode == 4:
            self.input = self.answers.pop(0) if self.answers else 0
            if not 0 <= self.input < len(words["K"]):
                raise RRFError("no such choice")
        elif mode == 5:
            self.input = self.answers.pop(0) if self.answers else words.get("F", 0)
        elif mode not in (0, 1):
            raise RRFError(f"M291 S{mode} is not in the stand-in")

    # --- For tests ----------------------------------------------------------------------------

    def heater_target(self, h: int) -> float:
        heater = self.heaters[h]
        return {"active": heater["active"], "standby": heater["standby"], "off": 0.0}[
            heater["state"]]
