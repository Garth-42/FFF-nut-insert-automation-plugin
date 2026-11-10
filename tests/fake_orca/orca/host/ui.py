import enum

from .. import _fake


class NotificationLevel(enum.Enum):
    WarningNotificationLevel = 1
    ErrorNotificationLevel = 2


class DockPanel:
    def __init__(self, html, title, on_message, on_close):
        self.html, self.title = html, title
        self.on_message, self.on_close = on_message, on_close
        self.posted, self.open = [], True

    def post(self, payload):
        _fake.ui_call()
        self.posted.append(payload)

    def show(self):
        self.open = True

    def hide(self):
        self.open = False

    def is_open(self):
        return self.open

    def close(self):
        self.open = False


def create_dock_panel(html, title="", width=0, height=0, on_message=None, on_close=None,
                      dock="right"):
    _fake.ui_call()
    panel = DockPanel(html, title, on_message, on_close)
    _fake.panels.append(panel)
    return panel


def push_notification(level, message):
    _fake.ui_call()
    _fake.notifications.append((level, message))
