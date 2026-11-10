from ._base import CapabilityBase


class ScriptPluginCapabilityBase(CapabilityBase):
    def execute(self):
        raise NotImplementedError
