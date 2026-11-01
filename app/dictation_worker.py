"""Local anonymous-pipe worker. Audio/text never go to a console, file or socket."""
import argparse
import array
import collections
import gc
import json
import math
import os
from pathlib import Path
import queue
import struct
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from offline_policy import require_dedicated_host
from inference_guard import audit, disable_ort_telemetry, DENIED

RATE = 16000
MAX_PACKET = 65536

def read_exact(stream, count):
    data = bytearray()
    while len(data) < count:
        part = stream(count-len(data)) if callable(stream) else stream.read(count-len(data))
        if not part:
            raise EOFError
        data.extend(part)
    return bytes(data)

def encode_command(kind, session=0, payload=b''):
    body = kind.encode('ascii') + struct.pack('<I', session) + payload
    return struct.pack('<I', len(body)) + body

class Recognizer:
    def __init__(self, settings, emit):
        self.settings = settings
        self.emit = emit
        self.recognizer = None
        self.runtime = None

    def load(self):
        if self.recognizer is not None:
            return
        lib = ROOT/'runtime/python/sherpa_onnx/lib'
        self.emit({'kind':'engine_phase','step':'telemetry'})
        if self.runtime is None:
            self.search = os.add_dll_directory(str(lib))
            self.runtime = disable_ort_telemetry(lib/'onnxruntime.dll')
        self.emit({'kind':'engine_phase','step':'numpy'})
        import numpy
        self.emit({'kind':'engine_phase','step':'sherpa'})
        import sherpa_onnx
        self.emit({'kind':'engine_phase','step':'model'})
        self.recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
            model=str(ROOT/'models/sensevoice/model.int8.onnx'),
            tokens=str(ROOT/'models/sensevoice/tokens.txt'),
            language='zh', use_itn=True, num_threads=self.settings['threads'],
            provider='cpu', debug=False)
        self.emit({'kind':'engine_phase','step':'loaded','telemetry_disabled':True})

    def decode(self, raw):
        self.load()
        import numpy as np
        samples = np.frombuffer(raw, dtype='<i2').astype(np.float32)/32768
        stream = self.recognizer.create_stream()
        stream.accept_waveform(RATE, samples)
        self.recognizer.decode_stream(stream)
        return stream.result.text.strip()

    def unload(self):
        self.recognizer = None
        gc.collect()

class Segmenter:
    """Energy gate, short live previews, final text after silence; bounded RAM."""
    def __init__(self, recognizer, emit, settings):
        self.recognizer, self.emit, self.settings = recognizer, emit, settings
        self.session = 0
        self.active = False
        self.noise = 0.002
        self.reset()

    def reset(self):
        self.raw = bytearray()
        self.pre = collections.deque(maxlen=3)
        self.speech = 0
        self.silence = 0
        self.last_preview = 0
        self.last_text = ''
        self.last_decoded_bytes = 0

    def start(self, session):
        self.reset()
        self.session = session
        self.active = True
        self.emit({'kind':'listening','session':session})

    def finish(self):
        if len(self.raw) >= RATE*.20*2 and self.speech >= RATE*.15:
            raw = bytes(self.raw)
            start = time.perf_counter()
            text = self.last_text if self.last_decoded_bytes == len(raw) else self.recognizer.decode(raw)
            self.emit({'kind':'final','session':self.session,'text':text,
                       'decode_ms':round((time.perf_counter()-start)*1000)})
        self.reset()

    def feed(self, session, raw):
        if not self.active or session != self.session:
            return
        samples = array.array('h', raw)
        if not samples:
            return
        rms = math.sqrt(sum(float(x)*x for x in samples)/len(samples))/32768
        threshold = max(self.settings['energy_threshold'], min(self.noise*3, .04))
        speaking = rms >= threshold
        if not self.raw and not speaking:
            self.noise = .98*self.noise + .02*rms
            self.pre.append(raw)
            return
        if not self.raw:
            self.raw.extend(b''.join(self.pre))
            self.pre.clear()
        self.raw.extend(raw)
        if speaking:
            self.speech += len(samples)
            self.silence = 0
        else:
            self.silence += len(samples)
        seconds = len(self.raw)/(RATE*2)
        if (self.silence >= RATE*self.settings['silence_ms']/1000
                or seconds >= self.settings['max_sentence_seconds']):
            self.finish()
        elif self.speech >= RATE*.35 and seconds-self.last_preview >= self.settings['preview_seconds']:
            self.last_preview = seconds
            self.last_text = self.recognizer.decode(bytes(self.raw))
            self.last_decoded_bytes = len(self.raw)
            self.emit({'kind':'partial','session':self.session,'text':self.last_text})

    def stop(self, session):
        if self.active and session == self.session:
            self.finish()
            self.active = False
            self.emit({'kind':'stopped','session':session})

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--pipe-token', required=True)
    args = parser.parse_args()
    require_dedicated_host()
    # Refuse an interactive console. Only the native app's anonymous pipes are used.
    import ctypes, msvcrt
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetFileType.argtypes = [ctypes.c_void_p]
    kernel.ReadFile.argtypes = [ctypes.c_void_p,ctypes.c_void_p,ctypes.c_uint32,
                                ctypes.POINTER(ctypes.c_uint32),ctypes.c_void_p]
    kernel.ReadFile.restype = ctypes.c_int
    stdin_handle = msvcrt.get_osfhandle(sys.stdin.fileno())
    def pipe_read(count):
        # Native ReadFile avoids holding a CRT file lock during a blocking read.
        # Such a lock can deadlock Windows extension-DLL initialization (NumPy).
        buffer = ctypes.create_string_buffer(count)
        got = ctypes.c_uint32()
        if not kernel.ReadFile(stdin_handle,buffer,count,ctypes.byref(got),None):
            raise EOFError
        return buffer.raw[:got.value]
    for stream in (sys.stdin, sys.stdout):
        if kernel.GetFileType(msvcrt.get_osfhandle(stream.fileno())) != 3:
            raise SystemExit('PIPE_REQUIRED')
    settings = json.loads((ROOT/'app/settings.json').read_text(encoding='utf-8'))
    assert 1 <= settings['threads'] <= 4
    assert .001 <= settings['energy_threshold'] <= .1
    assert 300 <= settings['silence_ms'] <= 2000
    assert .6 <= settings['preview_seconds'] <= 5
    assert 3 <= settings['max_sentence_seconds'] <= 20
    assert 10 <= settings['unload_seconds'] <= 600
    for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):
        os.environ[name] = str(settings['threads'])
    sys.addaudithook(audit)
    for name in ('requests','urllib.request','http.client','websockets','pip','huggingface_hub'):
        sys.modules[name] = None
    output = sys.stdout.buffer
    def emit(message):
        output.write(json.dumps(message, ensure_ascii=False).encode('utf-8')+b'\n')
        output.flush()
    inbox = queue.Queue(maxsize=400)
    def reader():
        try:
            while True:
                size = struct.unpack('<I', read_exact(pipe_read, 4))[0]
                if not 5 <= size <= MAX_PACKET:
                    break
                body = read_exact(pipe_read, size)
                inbox.put((chr(body[0]), struct.unpack('<I', body[1:5])[0], body[5:]))
        except (EOFError, OSError):
            pass
        finally:
            inbox.put(('X',0,b''))
    # Initialize extension modules before starting a blocking IPC thread.
    # Model weights are still loaded only when speech is first decoded.
    import numpy
    threading.Thread(target=reader, daemon=True).start()
    recognizer = Recognizer(settings, emit)
    segmenter = Segmenter(recognizer, emit, settings)
    authenticated = False
    idle = time.monotonic()
    emit({'kind':'ready','offline':True,'microphone':False})
    try:
        while True:
            try:
                kind, session, payload = inbox.get(timeout=1)
            except queue.Empty:
                if not segmenter.active and recognizer.recognizer is not None and time.monotonic()-idle >= settings['unload_seconds']:
                    recognizer.unload()
                    emit({'kind':'unloaded'})
                continue
            if kind == 'X':
                break
            if not authenticated:
                if kind != 'H' or payload.decode('ascii') != args.pipe_token:
                    raise ValueError('Invalid pipe handshake')
                authenticated = True
                continue
            if kind == 'S':
                segmenter.start(session)
            elif kind == 'A':
                segmenter.feed(session, payload)
            elif kind == 'E':
                segmenter.stop(session)
                idle = time.monotonic()
            elif kind == 'U' and not segmenter.active:
                recognizer.unload()
                emit({'kind':'unloaded'})
            elif kind == 'Q':
                break
    except Exception:
        # No exception arguments, frames or recognized text are logged.
        emit({'kind':'error','code':'RECOGNIZER_FAILED'})
    finally:
        recognizer.unload()
        emit({'kind':'closed','blocked_events':DENIED})

if __name__ == '__main__':
    main()
