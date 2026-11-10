from ._base import CapabilityBase


class PagesPluginCapabilityBase(CapabilityBase):
    def get_ui(self):
        return ""

    def on_message(self, data):
        pass

    def post_message(self, data):
        if not hasattr(self, "posted"):
            self.posted = []
        self.posted.append(data)
