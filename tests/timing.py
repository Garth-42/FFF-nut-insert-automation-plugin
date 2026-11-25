"""Time limits for tests that hold the plugin to CLAUDE.md rule 6 (handlers under 100 ms).

The limits are for the person's own computer. A shared CI machine is slower and busier,
so CI sets TIME_BUDGET_SCALE (the workflow uses 3) rather than letting the tests fail at
random; on a desk the limits stay as written.
"""

import os


def budget(seconds: float) -> float:
    """seconds, scaled by TIME_BUDGET_SCALE when it is set."""
    return seconds * float(os.environ.get("TIME_BUDGET_SCALE", "1"))
