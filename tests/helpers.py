"""Shared test helpers for FocusQuest."""

from focusquest.timer.engine import TimerEngine


class SignalCollector:
    """Utility to capture pyqtSignal emissions into a list."""

    def __init__(self):
        self.items: list = []

    def slot(self, *args):
        self.items.append(args if len(args) > 1 else args[0] if args else None)

    def __call__(self, *args):
        self.slot(*args)

    def __len__(self):
        return len(self.items)

    def __getitem__(self, idx):
        return self.items[idx]

    @property
    def last(self):
        return self.items[-1] if self.items else None

    def clear(self):
        self.items.clear()


def complete_session(engine: TimerEngine) -> None:
    """Fast-complete the current session by jumping to the last tick."""
    engine._remaining = 1
    engine._on_tick()
