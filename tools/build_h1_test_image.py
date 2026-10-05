"""Build a private H1 test NAND from a local dump; never modifies the dump.

The V1.41 FTL layout is derived from project.bin's scan at 0x80048a64:
128 pages/unit, OOB 1/2 commit page, 58 generation, 60 logical tag.
Requires the user-supplied emulator checkout in .tools/h1-emulator.
"""
import argparse
import ctypes
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
EMU = ROOT / '.tools/h1-emulator'
sys.path.insert(0, str(EMU))
sys.path.insert(0, str(ROOT / 'tests'))
from tools import make_fat16_image as fat16
from emu.qemu.ecc import jz4740_rs_encode
from make_test_rom import make_rom

PAGE, STRIDE, PAGES, UNITS = 2048, 2112, 128, 4096
UNIT = PAGE * PAGES


def encoder(work):
    """Compile the emulator's RS encoder for fast, unchanged parity generation."""
    original = (EMU / 'qemu/overlay/hw/mem/jz4740_ecc.c').read_text(encoding='utf-8')
    body = original[original.index('#define JZ4740_RS_SYMBOL_BITS'):original.index('static void rs_unpack_parity(')]
    body += original[original.index('void jz4740_rs_encode('):original.index('int jz4740_rs_decode(')]
    source = work / 'ecc.c'
    source.write_text('#include <stdint.h>\n#include <stddef.h>\n#include <string.h>\n'
                      '#define JZ4740_ECC_BLOCK_BYTES 512\n#define JZ4740_RS_PARITY_BYTES 9\n'
                      'static void stl_le_p(uint8_t *p, uint32_t n) { for(int i=0;i<4;i++) p[i]=(uint8_t)(n>>(8*i)); }\n'
                      + body, encoding='utf-8')
    dll = work / 'ecc.dll'
    gcc = os.environ.get('HOST_CC') or shutil.which('gcc')
    if not gcc: raise RuntimeError('Set HOST_CC or install a host gcc')
    subprocess.run([gcc, '-O2', '-shared', str(source), '-o', str(dll)], check=True)
    native = ctypes.CDLL(str(dll))
    native.jz4740_rs_encode.argtypes = [ctypes.c_char_p, ctypes.c_void_p]

    @lru_cache(maxsize=16384)
    def encode(data):
        output = ctypes.create_string_buffer(9)
        native.jz4740_rs_encode(data, output)
        return output.raw

    for data in [bytes(512), b'\xff' * 512, bytes(range(256)) * 2]:
        assert encode(data) == jz4740_rs_encode(data)
    return encode


def write_unit(stream, physical, logical, data, encode, last=127):
    stream.seek(physical * PAGES * STRIDE)
    for page in range(PAGES):
        payload = data[page * PAGE:(page + 1) * PAGE].ljust(PAGE, b'\xff')
        oob = bytearray(b'\xff' * 64)
        if page <= last:
            for chunk in range(4):
                oob[4 + chunk * 9:13 + chunk * 9] = encode(payload[chunk * 512:(chunk + 1) * 512])
            oob[1] = 0
            struct.pack_into('<H', oob, 2, last)
            struct.pack_into('<H', oob, 58, 1)
            struct.pack_into('<I', oob, 60, logical if logical == 0x38746262 else 0xffff0000 | logical)
        stream.write(payload + oob)


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dump', type=Path, required=True)
    parser.add_argument('--kernel', type=Path, required=True)
    parser.add_argument('--rom', type=Path, action='append', default=[])
    parser.add_argument('--reuse-stage', action='store_true')
    parser.add_argument('--bda', type=Path, default=ROOT/'dist/H1GBA.bda')
    parser.add_argument('--work-dir', type=Path, default=ROOT/'build/h1-emulator-test',
                        help='Private output directory for an independent firmware test image')
    args = parser.parse_args()
    work = args.work_dir.resolve()
    work.mkdir(parents=True, exist_ok=True)
    stage = work / 'files'
    if stage.exists() and not args.reuse_stage:
        raise FileExistsError('Use the existing test image or a fresh staging directory')
    dump = args.dump.resolve()
    assert dump != stage.resolve() and dump not in stage.resolve().parents
    # Calibration coefficients belong to the physical touchscreen. Let the
    # emulator's frontend calibrate its own ADC axes on this private image.
    calibration = stage / '系统/数据/SysTp.cfg'
    if calibration.exists():
        calibration.unlink()
    copied, skipped = 0, 0
    for source in dump.rglob('*'):
        if not source.is_file():
            continue
        relative = source.relative_to(dump)
        parts = relative.parts
        keep = parts[0] == '系统' and source.suffix.upper() != '.DCT' and '词典' not in source.name
        keep = keep or (len(parts) >= 2 and parts[:2] == ('应用', '程序'))
        keep = keep or (len(parts) >= 3 and parts[:3] == ('应用', '数据', '游戏') and source.name.lower().startswith('pet'))
        if source.name.casefold() == 'systp.cfg':
            keep = False
        if not keep:
            skipped += source.stat().st_size
            continue
        target = stage / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        copied += source.stat().st_size
    # Reuse the verified native menu slot so the firmware can discover the app.
    shutil.copyfile(args.bda, stage / '应用/程序/黑白子.bda')
    gba = stage / 'GBA'
    gba.mkdir(exist_ok=True)
    (gba / 'H1TEST.gba').write_bytes(make_rom())
    for rom in args.rom:
        shutil.copyfile(rom, gba / rom.name)
    kernel = work / 'project.bin'
    shutil.copyfile(args.kernel, kernel)
    root = fat16.build_tree(list(stage.iterdir()))
    # H1 V1.41 derives FAT cluster count from FTL capacity, ignoring BPB capacity.
    # With 4096 units, 16 MiB reserved, one BBT and 3% reserve: 0x1e8a00 sectors.
    # Native H1 writes reject LBAs below 512. The actual H1 USB volume has
    # 480 reserved sectors; with its 32-sector prefix FAT begins at LBA 512.
    # The 9588 image builder defaults to one reserved sector, which deadlocks
    # H1's FAT update after its failed write retains the FTL semaphore.
    fat16.RESERVED_SECTORS = 480
    fat = fat16.build_image(root, 'H1GBA', 0, 32, 4096, 32, 0x1e89e0)
    (work / 'logical-fat.img').write_bytes(fat)
    encode = encoder(work)
    nand = work / 'h1-system.raw'
    with nand.open('wb') as stream:
        erased = b'\xff' * (16 * 1024 * 1024)
        remaining = UNITS * PAGES * STRIDE
        while remaining:
            count = min(remaining, len(erased))
            stream.write(erased[:count])
            remaining -= count
        # BBT records all units as usable, with two committed data pages.
        write_unit(stream, 64, 0x38746262, b'\xff' * 4096, encode, last=1)
        mapped = []
        physical = 65
        for logical, offset in enumerate(range(0, len(fat), UNIT)):
            data = fat[offset:offset + UNIT].ljust(UNIT, b'\x00')
            if not any(data):
                continue
            write_unit(stream, physical, logical, data, encode)
            mapped.append({'logical': logical, 'physical': physical})
            physical += 1
        stream.flush()
    report = {'dump_modified': False, 'copied_bytes': copied, 'omitted_bytes': skipped,
              'nand': str(nand), 'nand_bytes': nand.stat().st_size, 'mapped_units': mapped,
              'kernel_sha256': hashlib.sha256(kernel.read_bytes()).hexdigest(),
              'bda_sha256': hashlib.sha256((args.bda).read_bytes()).hexdigest(),
              'ftl_layout': 'V1.41 firmware-derived; runtime validation required'}
    (work / 'image-build.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k != 'mapped_units'}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
