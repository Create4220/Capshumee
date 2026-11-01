"""Fail-closed policy shared by the local setup and inference entry points."""
import json
import ctypes
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]

def enforce_offline():
    policy = json.loads((ROOT / 'offline-policy.json').read_text(encoding='utf-8'))
    required = {
        'schema_version': 1, 'offline_only': True, 'selected_model': 'sensevoice',
        'allow_downloads': False, 'allow_update_checks': False,
        'allow_remote_transcription': False, 'allow_servers': False,
        'allow_telemetry': False, 'require_dedicated_python': True,
        'require_firewall': True,
    }
    for key, value in required.items():
        if type(policy.get(key)) is not type(value) or policy[key] != value:
            raise PermissionError('Offline policy missing or changed: ' + key)
    return policy

def reject_network_setup():
    enforce_offline()
    raise SystemExit('OFFLINE_ONLY: model downloads and online metadata/update checks are disabled by user request.')

def require_dedicated_host():
    enforce_offline()
    host = ROOT / 'runtime/host/asr-python.exe'
    if Path(sys.executable).resolve() != host.resolve():
        raise PermissionError('Use run-local.ps1 and the dedicated, network-blocked ASR Python host.')

def require_local_path(value):
    raw = str(value)
    if raw.startswith(('\\\\','//')) or '://' in raw:
        raise PermissionError('Network locations and URLs are disabled.')
    absolute = Path(value).absolute()
    get_drive_type = ctypes.WinDLL('kernel32').GetDriveTypeW
    get_drive_type.argtypes = [ctypes.c_wchar_p]
    get_drive_type.restype = ctypes.c_uint
    if get_drive_type(absolute.anchor) not in (2, 3, 5, 6):
        raise PermissionError('Only local storage is allowed; mapped network drives are disabled.')
    return absolute
