"""One editable recording draft; no external insertion and no persistence."""
class DraftSession:
    def __init__(self):
        self.session=0;self.active=False;self.finished=False;self.parts=[]
        self.displayed='';self.used=[]
    @property
    def raw(self):return ''.join(self.parts)
    def begin(self,session):
        self.session=session;self.active=True;self.finished=False;self.parts=[]
        self.displayed='';self.used=[]
    def accepts(self,session):
        return self.active and not self.finished and session==self.session
    def append(self,session,text):
        if not self.accepts(session):return False
        self.parts.append(text);return True
    def finish(self,session,displayed,used=()):
        if not self.accepts(session):return False
        self.finished=True;self.displayed=displayed;self.used=list(used);return True
    def cancel(self):
        self.active=False;self.finished=False;self.parts=[];self.displayed='';self.used=[]

