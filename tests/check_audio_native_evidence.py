"""Check full-firmware audio captures and a separate clean-exit run."""
from pathlib import Path
import hashlib
import json
import re
import struct
import wave

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'build/h1-emulator-test'
EVIDENCE = WORK / 'evidence'


def recording(name):
    with wave.open(str(EVIDENCE / name), 'rb') as stream:
        assert stream.getnchannels() == 2 and stream.getsampwidth() == 2
        assert stream.getframerate() == 32000
        count = stream.getnframes()
        samples = struct.unpack('<%dh' % (count * 2), stream.readframes(count))[::2]
    assert min(samples) < -1000 and max(samples) > 1000
    assert sum(x != 0 for x in samples) > count // 2
    runs, zero = [], 0
    for sample in samples:
        if sample == 0:
            zero += 1
        elif zero:
            runs.append(zero)
            zero = 0
    if zero:
        runs.append(zero)
    return samples, {
        'sample_rate': 32000, 'seconds': count / 32000,
        'min': min(samples), 'max': max(samples),
        'nonzero_fraction': sum(x != 0 for x in samples) / count,
        'max_silence_ms': max(runs, default=0) / 32,
    }


def main():
    # Historical v0.5 captures must not be attributed to a newer release.
    archive = ROOT / 'build/baseline-v05'
    sha = hashlib.sha256((archive / 'H1GBA.bda').read_bytes()).hexdigest()
    assert sha == 'f29555ab4343a1c77b39d8db8f721c048a2ef295662624eb8e84644f03122061'
    assert sha == json.loads((archive / 'H1GBA.build.json').read_text())['sha256']
    captures = (EVIDENCE / 'v05-sound-captures.log').read_bytes().decode('gbk')
    assert 'APP_BEGIN version=0.5' in captures
    assert captures.count('AUDIO_OPEN_END ready=1') >= 2
    closes = re.findall(r'AUDIO_CLOSE_BEGIN batches=(\d+) submitted=(\d+) nonzero=(\d+) '
                        r'dropped=(\d+) failures=(\d+) underruns=(\d+)', captures)
    assert len(closes) >= 2
    assert all(int(row[2]) > 0 and row[3:5] == ('0', '0') for row in closes[:2])
    assert captures.count('AUDIO_CLOSE_END descriptors=1') >= 2
    assert captures.count('GUI_CONTEXT_CLOSE_END') >= 2
    stops = re.findall(r'STOP video=(\d+) errors=(\d+)', captures)
    assert len(stops) >= 2 and all(row[1] == '0' for row in stops[:2])
    paths = [bytes.fromhex(s).decode('gbk') for s in re.findall(
        r'ROM_PATH_HEX offset=0 bytes=([0-9A-F]+)', captures)]
    assert paths[0].endswith('AUDIO.gba') and any(ord(c) > 127 for c in paths[1])

    clean = (EVIDENCE / 'v05-clean-exit.log').read_bytes().decode('gbk')
    assert 'APP_BEGIN version=0.5' in clean and 'APP_END result=0' in clean
    assert 'SAVE_LOAD_END status=1' in clean and 'SAVE_EXIT_END status=' in clean
    assert clean.count('AUDIO_OPEN_END ready=1') == clean.count('AUDIO_CLOSE_END descriptors=1') == 1
    assert 'GUI_CONTEXT_CLOSE_END' in clean and 'AUDIO_STALL' not in clean
    assert 'failures=0' in clean and 'errors=0' in clean

    samples, tone = recording('v05-final-tone.wav')
    assert tone['seconds'] >= 12
    crossings = [i for i in range(1, len(samples)) if samples[i - 1] <= 0 < samples[i]]
    periods = [b - a for a, b in zip(crossings, crossings[1:]) if 28 <= b - a <= 35]
    assert len(periods) > 5000
    tone['frequency_hz'] = 32000 * len(periods) / sum(periods)
    assert 1010 < tone['frequency_hz'] < 1040
    _, emerald = recording('v05-final-emerald.wav')
    assert emerald['seconds'] >= 15
    report = {
        'ok': True, 'kind': 'H1 V1.41 firmware with actual QEMU AIC PCM stream',
        'build_sha256': sha, 'tone': tone, 'emerald': emerald,
        'capture_runs': [dict(zip(('batches', 'submitted', 'nonzero', 'dropped', 'failures', 'underruns'),
                                 map(int, row))) for row in closes[:2]],
        'clean_exit_and_audio_close': True, 'save_restored': True,
        'hardware_tested': False, 'uninterrupted_playback': False,
    }
    output = EVIDENCE / 'audio-native-verification.json'
    output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(output.read_text())


if __name__ == '__main__':
    main()
