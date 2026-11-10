"""Test helpers for the stand-in orca module. Not part of the real API."""

import numpy as np

plugin_classes = []
registered = []
panels = []
notifications = []
permission_requests = []   # filled once, when the plugin module is imported
in_slicing_step = False   # set by tests; orca.host.ui then refuses calls, like a deadlock


class Mesh:
    def __init__(self, vertices, triangles):
        self._v = np.asarray(vertices, dtype=np.float32)
        self._t = np.asarray(triangles, dtype=np.int32)
        self._v.flags.writeable = False
        self._t.flags.writeable = False

    def vertices(self):
        return self._v

    def triangles(self):
        return self._t


class Volume:
    def __init__(self, name, vertices, triangles, matrix, kind="part"):
        self.name = name
        self.kind = kind
        self._mesh = Mesh(vertices, triangles)
        self._matrix = np.asarray(matrix, dtype=np.float64)

    def mesh(self):
        return self._mesh

    def is_modifier(self):
        return self.kind == "modifier"

    def is_model_part(self):
        return self.kind == "part"

    def matrix(self):
        return self._matrix


class Instance:
    def __init__(self, matrix, left_handed=False):
        self._matrix = np.asarray(matrix, dtype=np.float64)
        self._left = left_handed

    def matrix(self):
        return self._matrix

    def is_left_handed(self):
        return self._left


class Object:
    def __init__(self, volumes, instances):
        self._volumes, self._instances = list(volumes), list(instances)

    def volumes(self):
        return self._volumes

    def instances(self):
        return self._instances


class Model:
    def __init__(self, objects=()):
        self._objects = list(objects)

    def objects(self):
        return self._objects


class Ctx:
    """The context a slicing step receives."""

    def __init__(self, step, gcode_path=None, config=None):
        self.step = step
        self.gcode_path = gcode_path
        self.print = None
        self.object = None
        self._config = config or {}

    def config_value(self, key):
        return self._config[key]


current_model = Model()


def _kind(part):
    """Parts built without a kind: nut bodies are modifiers, the rest print."""
    if part.kind != "unknown":
        return part.kind
    return "modifier" if "NUT_" in part.name.upper() else "part"


def set_model(snapshot):
    """Load a nutcore ModelSnapshot as the fake model."""
    global current_model
    current_model = Model(
        Object([Volume(p.name, p.vertices, p.triangles, p.matrix, _kind(p))
                for p in obj.parts],
               [Instance(i.matrix, i.mirrored) for i in obj.instances])
        for obj in snapshot.objects)


def ui_call():
    if in_slicing_step:
        raise RuntimeError("orca.host.ui called from a slicing step: this can deadlock")


def reset():
    global current_model, in_slicing_step
    current_model = Model()
    in_slicing_step = False
    for items in (registered, panels, notifications):   # plugin_classes fill once, at import
        items.clear()
