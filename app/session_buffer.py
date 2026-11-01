"""One Caps Lock cycle. Only confirmed text, no persistence or clipboard mid-session."""

class SessionBuffer:
    def __init__(self):
        self.begin(0, (None,None))
        self.finished = True

    def begin(self, session, target):
        self.session = session
        self.target = target
        self.parts = []
        self.fallback = False
        self.stop_requested = False
        self.finished = False

    @property
    def text(self):
        return ''.join(self.parts)

    def accepts(self, session):
        return session == self.session and not self.finished

    def target_changed(self):
        if not self.finished:
            self.fallback = True

    def final(self, session, text, insert):
        if not self.accepts(session):
            return 'stale'
        if not text:
            return 'empty'
        self.parts.append(text)
        if not self.fallback:
            if insert(text,self.target):
                return 'inserted'
            self.fallback = True
        return 'fallback'

    def stopping(self, session, same_target):
        if self.accepts(session):
            self.stop_requested = True
            if not same_target:self.fallback = True

    def complete(self, session, copy=None):
        if not self.accepts(session) or not self.stop_requested:
            return 'stale'
        self.finished = True
        if not self.text:
            return 'empty'
        if self.fallback:
            return 'buffered'
        return 'inserted'

    def retry_copy(self, copy):
        if self.finished and self.text:
            return copy(self.text)
        return False
