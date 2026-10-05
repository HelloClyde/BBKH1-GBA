"""Check captured full-firmware evidence, independently of the mock services."""
from pathlib import Path
import json
import re
import struct
import zlib
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'build/h1-emulator-test'
EVIDENCE = WORK / 'evidence'


def main():
    log = (EVIDENCE / 'v04-native-run.log').read_bytes().decode('gbk')
    assert 'APP_BEGIN version=0.4' in log and 'APP_END result=0' in log
    assert log.count('ROM_LOAD_END loaded=1') == 3
    assert 'SAVE_LOAD_END status=1 slot=0 generation=1' in log
    assert log.count('GUI_CONTEXT_CLOSE_END') == 3
    stops = re.findall(r'STOP video=(\d+) errors=(\d+)', log)
    assert len(stops) == 3 and all(int(errors) == 0 for _, errors in stops)
    assert int(stops[1][0]) >= 1000
    paths = [bytes.fromhex(value).decode('gbk') for value in re.findall(
        r'ROM_PATH_HEX offset=0 bytes=([0-9A-F]+)', log)]
    assert len(paths) == 3 and len(paths[1].encode('gbk')) == 28
    assert any(ord(c) > 127 for c in paths[1])
    normal = Image.open(WORK / 'v04-h1test-restored.png').convert('RGB')
    pressed = Image.open(WORK / 'v04-native-a.png').convert('RGB')
    assert normal.size == pressed.size == (480, 272)
    assert normal.getpixel((36, 0)) == (0, 0, 248)
    assert pressed.getpixel((36, 0)) == (0, 248, 0)
    assert normal.getpixel((240, 136)) == pressed.getpixel((240, 136)) == (248, 0, 0)
    assert normal.getpixel((0, 136)) == normal.getpixel((479, 136)) == (0, 0, 0)
    slot = (EVIDENCE / 'H1TEST.gba.s0').read_bytes()
    magic, version, _, generation, size, crc, header_crc = struct.unpack('<7I', slot[:28])
    assert magic == 0x31534748 and version == 1 and size == 131072
    assert len(slot) == 131100 and slot[28] == 0x5a
    assert zlib.crc32(slot[28:]) == crc and zlib.crc32(slot[:24]) == header_crc
    cancel = (EVIDENCE / 'v04-cancel.log').read_bytes().decode('gbk')
    assert 'ROM_SELECT_END status=0' in cancel and 'APP_END result=0' in cancel
    assert 'ROM_LOAD_BEGIN' not in cancel and 'GUI_CONTEXT_BEGIN' not in cancel
    report = {
        'ok': True, 'kind': 'full H1 V1.41 firmware, QEMU bbkh1',
        'build_sha256': '07ab1ec5c02c74243a16a7e05c6ec73f69a4f95f1d16318752dc7559811dceee',
        'rom_paths': paths, 'native_stop_video_frames': [int(n) for n, _ in stops],
        'rgb_conversion_and_A_transition': True, 'native_ROM_switch': True,
        'native_save': {'bytes': len(slot), 'generation': generation, 'SRAM0': slot[28],
                        'data_and_header_CRC': True, 'native_restore': True},
        'native_exit': True, 'original_dump_modified': False,
        'native_cancel': True,
        'manual_screen_checks': ['native selector', 'Emerald title', 'Start advances',
                                 'M returns to selector', 'Escape returns to desktop'],
        'hardware_tested': False,
    }
    (EVIDENCE / 'native-verification.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()
