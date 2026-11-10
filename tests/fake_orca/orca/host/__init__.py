from .. import _fake
from . import ui

__all__ = ["model", "ui"]


def model():
    return _fake.current_model
