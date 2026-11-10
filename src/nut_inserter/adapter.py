"""Every call into `orca.host`, and every Orca result object, is made here.

Orca says the plugin API may still change. Keeping the calls in this one small
module means a change in Orca is a change in this file only.
"""

import json

import numpy as np
import orca

from nutcore.mesh import (
    InstanceSnapshot,
    ModelSnapshot,
    ObjectSnapshot,
    PartSnapshot,
    make_snapshot,
)

# Whether pages receive a JSON string or an object is not documented. The probe
# (milestone 0) logs it. The pages accept both, so this only changes what is sent.
POST_AS_JSON_STRING = False


# --- Model ----------------------------------------------------------------------------------

def snapshot() -> ModelSnapshot:
    """Copy the live model into plain arrays. Keeps no reference to Orca objects."""
    objects = []
    for obj in orca.host.model().objects():
        parts = []
        for vol in obj.volumes():
            mesh = vol.mesh()
            name = vol.name() if callable(vol.name) else vol.name
            parts.append(PartSnapshot(
                name=str(name),
                vertices=np.array(mesh.vertices(), dtype=np.float64).reshape(-1, 3),
                triangles=np.array(mesh.triangles(), dtype=np.int32).reshape(-1, 3),
                matrix=np.array(vol.matrix(), dtype=np.float64).reshape(4, 4),
                kind=part_type(vol)))
        instances = [InstanceSnapshot(
            matrix=np.array(inst.matrix(), dtype=np.float64).reshape(4, 4),
            mirrored=bool(inst.is_left_handed())) for inst in obj.instances()]
        objects.append(ObjectSnapshot(parts=tuple(parts), instances=tuple(instances)))
    return make_snapshot(objects)


def part_type(volume) -> str:
    """The part's type: "part" (it prints), "modifier", "other" or "unknown".

    The documentation does not list these calls, but the probe found and ran
    them in OrcaSlicer 2.5.0 (docs/api-facts.md). Setting the type is still not
    possible, so the user changes a nut body to Modifier by hand.
    """
    try:
        if volume.is_modifier():
            return "modifier"
        return "part" if volume.is_model_part() else "other"
    except Exception:  # noqa: BLE001
        return "unknown"


# --- Results --------------------------------------------------------------------------------

def success(message=""):
    return orca.ExecutionResult.success(message)


def skipped(message=""):
    return orca.ExecutionResult.skipped(message)


def failure(message):
    return orca.ExecutionResult.failure(orca.PluginResult.RecoverableError, message)


# --- Settings -------------------------------------------------------------------------------

def read_config(owner):
    """The settings stored on a capability: a JSON string (or whatever Orca returns)."""
    return owner.get_config()


def save_config(owner, config: dict) -> bool:
    return bool(owner.save_config(json.dumps(config)))


# --- Pages, panel and notifications. Never call these from a slicing step. ------------------

def encode(payload: dict):
    return json.dumps(payload) if POST_AS_JSON_STRING else payload


def decode(data) -> dict:
    """A page message as a dict, whether Orca delivers an object or a JSON string."""
    if isinstance(data, (str, bytes)):
        data = json.loads(data)
    return dict(data) if data else {}


def create_panel(html, on_message, on_close):
    return orca.host.ui.create_dock_panel(html=html, title="Nut inserter", width=400, height=700,
                                          on_message=on_message, on_close=on_close, dock="right")


def post_panel(panel, payload: dict) -> None:
    panel.post(encode(payload))


def post_tab(tab, payload: dict) -> None:
    tab.post_message(encode(payload))


def notify(is_error: bool, message: str) -> None:
    levels = orca.host.ui.NotificationLevel
    level = levels.ErrorNotificationLevel if is_error else levels.WarningNotificationLevel
    orca.host.ui.push_notification(level, message)


def notify_info(message: str) -> None:
    orca.host.ui.push_notification(
        orca.host.ui.NotificationLevel.RegularNotificationLevel, message)


# --- Slicing context ------------------------------------------------------------------------

def config_value(ctx, key):
    """A print setting as text, or None. Key names are unverified, so never raise."""
    try:
        value = ctx.config_value(key)
        return None if value is None else str(value)
    except Exception:  # noqa: BLE001
        return None


def gcode_path(ctx) -> str:
    return str(ctx.gcode_path)
