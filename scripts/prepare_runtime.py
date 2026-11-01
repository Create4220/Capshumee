"""Bundle an existing local Python installation. No downloads or network calls."""
from pathlib import Path
import shutil
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
BASE=Path(sys.base_prefix)
HOST=ROOT/'runtime/host'
if sys.version_info[:2]!=(3,12):raise SystemExit('64-bit Python 3.12 required')
HOST.mkdir(parents=True,exist_ok=True)
for name in ('python.exe','python312.dll','python3.dll','vcruntime140.dll','vcruntime140_1.dll'):
    shutil.copy2(BASE/name,HOST/('asr-python.exe' if name=='python.exe' else name))
if (BASE/'LICENSE.txt').exists():shutil.copy2(BASE/'LICENSE.txt',ROOT/'runtime/PYTHON-LICENSE.txt')
shutil.copytree(BASE/'DLLs',ROOT/'runtime/stdlib-dlls',dirs_exist_ok=True)
exclude={'site-packages','__pycache__','test','tests','idlelib','tkinter','turtledemo','ensurepip'}
with zipfile.ZipFile(ROOT/'runtime/python-stdlib.zip','w',zipfile.ZIP_DEFLATED) as archive:
    for source in sorted((BASE/'Lib').rglob('*.py')):
        relative=source.relative_to(BASE/'Lib')
        if not any(part in exclude for part in relative.parts):archive.write(source,relative.as_posix())
(HOST/'python312._pth').write_text('..\\python-stdlib.zip\n..\\stdlib-dlls\n..\\python\n..\\..\\scripts\n',encoding='ascii')
print('Dedicated local runtime prepared. Configure firewall rules before starting.')
