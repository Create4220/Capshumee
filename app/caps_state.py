"""Reconcile sampled Windows Caps Lock state, never count keyboard events."""


class CapsState:
    def __init__(self):
        self.reset()

    def reset(self):
        # Startup/resume/pause require an observed OFF before a new ON.
        self.armed = False
        self.on_since = None
        self.last_sample = None

    def sample(self, on, held, available, recording, now):
        gap = self.last_sample is not None and now - self.last_sample > 2.0
        if gap:
            self.reset()
        self.last_sample = now
        if not available or on is None:
            self.reset()
            return 'stop' if recording else None
        if not on:
            self.on_since = None
            self.armed = not held
            return 'stop' if recording else None
        if gap:
            return 'stop' if recording else None
        if not self.armed:
            return None
        if self.on_since is None:
            self.on_since = now
        # Wait for key release and two separated ON samples. This prevents
        # stale callback-time state, repeat keys and delayed notifications
        # from creating a new recording. A failed start consumes this edge.
        if not held and now - self.on_since >= 0.02:
            self.armed = False
            self.on_since = None
            return None if recording else 'start'
        return None
