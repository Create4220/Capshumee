"""Local, bounded word corrections. Never stores recordings or complete drafts."""
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import threading
import time

_WORD=re.compile(r'^[A-Za-z\u3400-\u9fff][A-Za-z\u3400-\u9fff_-]{0,11}$')
def local_path():
    base=Path(os.environ.get('LOCALAPPDATA',str(Path.home()/'AppData/Local')))
    if str(base).startswith(('\\\\','//')):raise OSError('LOCAL_PREFERENCES_ONLY')
    from offline_policy import require_local_path
    return require_local_path(base/'Capshumee'/'preferences.json')

class PreferenceStore:
    def __init__(self,path=None):
        self.path=Path(path) if path else local_path()
        self.lock=threading.RLock();self.rules=[];self.enabled=True;self.writable=True;self.revision=0
        try:
            if self.path.exists():
                if self.path.stat().st_size>1024*1024:raise ValueError('STORE_SIZE')
                data=json.loads(self.path.read_text(encoding='utf-8'))
                if data.get('version')!=1:raise ValueError('STORE_VERSION')
                self.enabled=bool(data.get('enabled',True))
                for r in data.get('rules',[])[:1000]:
                    if self.valid(r):self.rules.append(r)
        except (OSError,ValueError,TypeError,KeyError,AttributeError):
            # Preserve an unreadable store; never overwrite it silently.
            self.writable=False
    @staticmethod
    def valid(r):
        return (isinstance(r,dict) and _WORD.fullmatch(str(r.get('source',''))) and
                _WORD.fullmatch(str(r.get('target',''))) and r['source']!=r['target'] and
                isinstance(r.get('id'),str) and len(r['id'])==20 and
                isinstance(r.get('count'),int) and 1<=r['count']<=1000000 and
                all(isinstance(r.get(k),str) and len(r[k])<=2 for k in ('left','right')) and
                isinstance(r.get('enabled'),bool))
    def save(self):
        if not self.writable:raise OSError('PREFERENCES_UNAVAILABLE')
        self.path.parent.mkdir(parents=True,exist_ok=True)
        temp=self.path.with_suffix('.tmp')
        try:
            temp.write_text(json.dumps({'version':1,'enabled':self.enabled,'rules':self.rules},
                                      ensure_ascii=False),encoding='utf-8')
            os.replace(temp,self.path)
        except OSError:
            try:temp.unlink(missing_ok=True)
            except OSError:pass
            raise
    def snapshot(self):
        with self.lock:return [dict(r) for r in self.rules]
    def set_enabled(self,value):
        with self.lock:
            before=self.enabled;self.enabled=bool(value);self.revision+=1
            try:self.save()
            except OSError:self.enabled=before;raise
    def delete(self,rule_id):
        with self.lock:
            before=self.rules;self.revision+=1;self.rules=[r for r in before if r['id']!=rule_id]
            try:self.save()
            except OSError:self.rules=before;raise
    def clear(self):
        with self.lock:
            before=self.rules;write_before=self.writable
            self.revision+=1;self.rules=[];self.writable=True
            try:self.save()
            except OSError:self.rules=before;self.writable=write_before;raise
    def apply(self,text):
        with self.lock:
            if not self.enabled:return text,[]
            rules=[dict(r) for r in self.rules if r['enabled']]
        matches=[]
        for r in rules:
            start=0
            while True:
                i=text.find(r['source'],start)
                if i<0:break
                j=i+len(r['source']);start=i+1
                # Latin source words must not match inside longer identifiers.
                if r['source'].isascii() and ((i and text[i-1].isascii() and text[i-1].isalnum()) or
                        (j<len(text) and text[j].isascii() and text[j].isalnum())):continue
                general=r['count']>=3 and len(r['source'])>=2
                context=(bool(r['left'] or r['right']) and
                         text[max(0,i-len(r['left'])):i]==r['left'] and
                         text[j:j+len(r['right'])]==r['right'])
                exact=(i==0 and j==len(text) and not r['left'] and not r['right'])
                if general or context or exact:
                    matches.append((i,j,r))
        # Apply against the original text once: no cascading A->B->C rewrites.
        matches.sort(key=lambda m:(m[0],-len(m[2]['source']),-m[2]['count'],-m[2].get('updated',0)))
        out=[];cursor=0;used=[]
        for i,j,r in matches:
            if i<cursor:continue
            out.extend((text[cursor:i],r['target']));cursor=j;used.append(r['id'])
        out.append(text[cursor:])
        return ''.join(out),used
    def learn(self,original,edited,displayed='',used=(),expected_revision=None):
        if len(original)>20000 or len(edited)>20000:return 0
        with self.lock:
            if not self.enabled or not self.writable:return 0
            if expected_revision is not None and self.revision!=expected_revision:return 0
            before=[dict(r) for r in self.rules]
            # Reject an applied correction when the user explicitly restores ASR.
            if original==edited and displayed!=edited:
                for r in self.rules:
                    if r['id'] in used:r['enabled']=False
            matcher=difflib.SequenceMatcher(None,original,edited,autojunk=True)
            opcodes=matcher.get_opcodes()
            changed=sum(max(b-a,d-c) for tag,a,b,c,d in opcodes if tag!='equal')
            learned=0;seen=set()
            if changed<=max(12,int(max(len(original),len(edited))*.4)):
                for tag,a,b,c,d in opcodes:
                    source,target=original[a:b],edited[c:d]
                    if tag!='replace' or not _WORD.fullmatch(source) or not _WORD.fullmatch(target):continue
                    # One isolated character without neighbours is ambiguous.
                    left=original[max(0,a-2):a];right=original[b:b+2]
                    if len(source)==1 and not (left or right):continue
                    key=(source,target,left,right)
                    if key in seen:continue
                    seen.add(key)
                    rid=hashlib.sha256(json.dumps(key,ensure_ascii=False).encode()).hexdigest()[:20]
                    entry=next((r for r in self.rules if r['id']==rid),None)
                    if entry is None:
                        entry=dict(id=rid,source=source,target=target,left=left,right=right,count=0,enabled=True)
                        self.rules.append(entry)
                    entry['count']=min(entry['count']+1,1000000);entry['enabled']=True;entry['updated']=time.time()
                    learned+=1
                    if learned>=20:break
            self.rules=sorted(self.rules,key=lambda r:r.get('updated',0),reverse=True)[:1000]
            if self.rules!=before:
                try:self.save()
                except OSError:self.rules=before;raise
            return learned

