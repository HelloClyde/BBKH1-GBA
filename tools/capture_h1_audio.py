"""Capture the local H1 emulator's actual AIC PCM stream as a WAV."""
import argparse
import base64
import importlib.util
import json
import os
from pathlib import Path
import socket
import struct
import time
import wave

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--seconds', type=float, default=15)
    args = parser.parse_args()
    emulator_root=Path(os.environ.get('H1_EMULATOR_ROOT',str(ROOT/'.tools/h1-emulator')))
    spec = importlib.util.spec_from_file_location('h1_audio_capture_protocol', emulator_root/'h1/h1_emulator.py')
    protocol = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(protocol)
    chunks, sample_rate = [], None
    with socket.create_connection(('127.0.0.1', 8793), timeout=5) as stream:
        key = base64.b64encode(b'H1GBAPCMCapture!').decode()
        stream.sendall(('GET /ws?stream=audio HTTP/1.1\r\nHost: 127.0.0.1:8793\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Key: ' + key + '\r\n\r\n').encode())
        header = b''
        while not header.endswith(b'\r\n\r\n'):
            header += stream.recv(1)
        if b' 101 ' not in header.split(b'\r\n')[0]:
            raise RuntimeError(header)
        deadline = time.monotonic() + args.seconds
        stream.settimeout(1)
        while time.monotonic() < deadline:
            try:
                opcode, packet = protocol.read_ws_frame(stream)
            except socket.timeout:
                continue
            if opcode != 2: continue
            magic, _, rate, channels, stride, fmt = struct.unpack_from('<4s5I', packet)
            assert magic == b'H1AU' and channels == 2 and stride == 4 and fmt == protocol.AUDIO_FORMAT_S16LE
            if sample_rate is not None and sample_rate != rate:
                raise ValueError('Sample rate changed during capture')
            sample_rate = rate
            chunks.append(packet[24:])
    if not chunks:
        raise RuntimeError('No native AIC audio packets received')
    pcm = b''.join(chunks)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(args.output), 'wb') as output:
        output.setnchannels(2); output.setsampwidth(2); output.setframerate(sample_rate); output.writeframes(pcm)
    values = struct.unpack('<' + 'h' * (len(pcm) // 2), pcm)
    report = {'sample_rate': sample_rate, 'frames': len(pcm) // 4, 'seconds': len(pcm) / (4 * sample_rate),
              'min': min(values), 'max': max(values), 'nonzero_samples': sum(v != 0 for v in values), 'packets': len(chunks)}
    args.output.with_suffix('.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
