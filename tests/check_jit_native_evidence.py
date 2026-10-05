"""Check the final JIT release's complete H1 firmware logs, PCM and native save."""
from pathlib import Path
import hashlib
import json
import re
import struct
import wave
import zlib
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'build/h1-emulator-test'
EVIDENCE = WORK / 'evidence'


def audio(name):
    with wave.open(str(EVIDENCE / name), 'rb') as stream:
        assert (stream.getframerate(), stream.getnchannels(), stream.getsampwidth()) == (32000, 2, 2)
        count = stream.getnframes()
        samples = struct.unpack('<%dh' % (count * 2), stream.readframes(count))[::2]
    assert count >= 32000 * 12 and min(samples) < -1000 and max(samples) > 1000
    fraction = sum(x != 0 for x in samples) / count
    assert fraction > .5
    return {'seconds': count / 32000, 'min': min(samples), 'max': max(samples),
            'nonzero_fraction': fraction}


def main():
    sha = hashlib.sha256((ROOT / 'build/v06-release/H1GBA.bda').read_bytes()).hexdigest()
    assert json.loads((EVIDENCE / 'jit-native-verification.json').read_text())['build_sha256'] == sha
    metadata = json.loads((ROOT / 'build/v06-release/H1GBA.build.json').read_text())
    assert metadata['sha256'] == sha and metadata['core'] == 'jit' and not metadata['benchmark']
    log = (EVIDENCE / 'v06-native-run.log').read_bytes().decode('gbk')
    assert 'APP_BEGIN version=0.6 diagnostics=1 core=JIT' in log and 'APP_END result=0' in log
    paths = [bytes.fromhex(s).decode('gbk') for s in re.findall(r'ROM_PATH_HEX offset=0 bytes=([0-9A-F]+)', log)]
    assert len(paths) == 3 and any(ord(c) > 127 for c in paths[0])
    assert paths[1] == paths[2] and paths[1].endswith('AUDIO.gba')
    assert log.count('JIT_STATE enabled=1') == log.count('JIT_FREE_END') == 3
    assert log.count('GUI_CONTEXT_CLOSE_END') == 3
    assert log.count('AUDIO_OPEN_END ready=1') == log.count('AUDIO_CLOSE_END descriptors=1') == 3
    assert 'AUDIO_STALL' not in log and 'SAVE_LOAD_END status=1' in log
    closes = re.findall(r'AUDIO_CLOSE_BEGIN batches=(\d+) submitted=(\d+) nonzero=(\d+) '
                        r'dropped=(\d+) failures=(\d+) underruns=(\d+)', log)
    assert len(closes) == 3 and all(row[4] == '0' for row in closes)
    syncs = re.findall(r'JIT_FREE_BEGIN .*sync_calls=(\d+) sync_bytes=(\d+)', log)
    assert len(syncs) == 3 and all(int(a) > 0 and int(b) > 0 for a, b in syncs)
    stops = re.findall(r'STOP video=(\d+) errors=(\d+)', log)
    assert len(stops) == 3 and all(int(a) > 5 and b == '0' for a, b in stops)
    assert int(stops[0][0]) >= 500
    slot = (EVIDENCE / 'v06-AUDIO.gba.s0').read_bytes()
    magic, version, _, generation, size, crc, header_crc = struct.unpack('<7I', slot[:28])
    assert magic == 0x31534748 and version == 1 and size == 131072
    assert len(slot) == 131100 and slot[28] == 0x5a
    assert zlib.crc32(slot[28:]) == crc and zlib.crc32(slot[:24]) == header_crc
    frame = Image.open(WORK / 'v06-tone.png').convert('RGB')
    assert frame.size == (480, 272) and frame.getpixel((36, 0)) == (0, 0, 248)
    assert frame.getpixel((240, 136)) == (248, 0, 0)
    pressed = Image.open(WORK / 'v06-tone-a.png').convert('RGB')
    assert pressed.getpixel((36, 0)) == (0, 248, 0)
    report = {
        'ok': True, 'kind': 'H1 V1.41 complete firmware, QEMU bbkh1, MIPS JIT',
        'build_sha256': sha, 'video_frames': [int(n) for n, _ in stops],
        'jit_enabled_for_all_ROMs': True, 'native_switch_exit_save_restore': True,
        'native_A_transition': True, 'save_generation': generation, 'save_CRC': True,
        'tone': audio('v06-tone.wav'), 'emerald': audio('v06-emerald.wav'),
        'audio_runs': [dict(zip(('batches', 'submitted', 'nonzero', 'dropped', 'failures', 'underruns'),
                               map(int, row))) for row in closes],
        'manual_screen_checks': ['Emerald intro', 'Start advances to battery prompt', 'new game menu', 'exit desktop'],
        'hardware_FPS_and_cache_behavior_tested': False,
    }
    output = EVIDENCE / 'jit-native-verification.json'
    output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(output.read_text())


if __name__ == '__main__':
    main()
