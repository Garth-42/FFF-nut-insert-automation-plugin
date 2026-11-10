import enum

from ._base import CapabilityBase


class Step(enum.Enum):
    posSlice = 1
    posPerimeters = 2
    psGCodePostProcess = 3


class SlicingPipelineCapabilityBase(CapabilityBase):
    def execute(self, ctx):
        raise NotImplementedError
