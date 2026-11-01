"""Local inference network/process guard and ONNX Runtime telemetry control."""
import ctypes as C
DENIED=[]

def audit(event,args):
    if event.startswith('socket.') or event in ('subprocess.Popen','os.system','os.exec','os.spawn'):
        DENIED.append(event)
        raise PermissionError('Network and external process launches are disabled in local inference: '+event)

def disable_ort_telemetry(library):
    """Use the documented, ABI-stable first slots of OrtApi v1.

    Reference: microsoft/onnxruntime include/onnxruntime/core/session/onnxruntime_c_api.h.
    Keep the shared OrtEnv alive for this worker's lifetime so sherpa uses the
    same environment with telemetry disabled. Process exit releases all memory.
    """
    dll=C.WinDLL(str(library))
    dll.OrtGetApiBase.restype=C.POINTER(C.c_void_p)
    base=dll.OrtGetApiBase()
    getapi=C.WINFUNCTYPE(C.POINTER(C.c_void_p),C.c_uint32)(base[0])
    version=C.WINFUNCTYPE(C.c_char_p)(base[1])().decode()
    api=getapi(1)
    if not api:raise RuntimeError('ONNX Runtime C API v1 unavailable')
    geterror=C.WINFUNCTYPE(C.c_char_p,C.c_void_p)(api[2])
    create=C.WINFUNCTYPE(C.c_void_p,C.c_int,C.c_char_p,C.POINTER(C.c_void_p))(api[3])
    disable=C.WINFUNCTYPE(C.c_void_p,C.c_void_p)(api[6])
    env=C.c_void_p()
    for status in (create(3,b'local-asr-no-telemetry',C.byref(env)),):
        if status:raise RuntimeError(geterror(status).decode())
    status=disable(env)
    if status:raise RuntimeError(geterror(status).decode())
    return dll,env,version
