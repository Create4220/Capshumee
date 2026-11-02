"""Build the complete offline payload from local files; never downloads anything."""
import argparse
import hashlib
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--runtime-source',type=Path,default=ROOT/'runtime')
parser.add_argument('--model-source',type=Path,default=ROOT/'models/sensevoice')
args=parser.parse_args()
runtime=args.runtime_source.resolve();model=args.model_source.resolve();out=ROOT/'.payload'
if out.exists():raise SystemExit('Generated .payload already exists. Use an empty build tree or the explicit prepared-payload option.')
with (model/'model.int8.onnx').open('rb') as stream:
    if hashlib.file_digest(stream,'sha256').hexdigest()!='c71f0ce00bec95b07744e116345e33d8cbbe08cef896382cf907bf4b51a2cd51':
        raise SystemExit('Unexpected model; verify provenance before updating the release model hash.')
out.mkdir()
def copy(source,destination):
    if source.is_symlink() or source.is_junction():raise ValueError('Linked files are not accepted in release input')
    destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,destination)
for name in ('dictation_app.py','dictation_worker.py','session_buffer.py','private_clipboard.py','caps_state.py','settings.json'):
    copy(ROOT/'app'/name,out/'app'/name)
for name in ('inference_guard.py','offline_policy.py','lock-network.ps1'):
    copy(ROOT/'scripts'/name,out/'scripts'/name)
for name in ('卡输咪.exe','run-local.ps1','offline-policy.json','LICENSE','README.md','THIRD_PARTY_NOTICES.md'):
    copy(ROOT/name,out/name)
for folder in ('assets','licenses','docs'):
    for source in (ROOT/folder).rglob('*'):
        if source.is_file():copy(source,out/folder/source.relative_to(ROOT/folder))
for name in ('asr-python.exe','python312.dll','python3.dll','vcruntime140.dll','vcruntime140_1.dll','python312._pth'):
    copy(runtime/'host'/name,out/'runtime/host'/name)
copy(runtime/'python-stdlib.zip',out/'runtime/python-stdlib.zip')
for folder in ('stdlib-dlls','python'):
    for source in (runtime/folder).rglob('*'):
        relative=source.relative_to(runtime/folder)
        if not source.is_file() or any(part in ('__pycache__','test','tests') or part.endswith('.data') for part in relative.parts) or source.suffix in ('.pyc','.pyo','.lib'):continue
        copy(source,out/'runtime'/folder/relative)
for name in ('model.int8.onnx','tokens.txt','LICENSE','README.md'):copy(model/name,out/'models/sensevoice'/name)
print('Complete offline payload prepared from local model and runtime files.')
