"""Trace the supplied H1 BBVM's real startup until GUI+0x9EC.

Does not execute BBVM bytecode or firmware: three service calls are trapped.
The original BDA stays on the user's drive and is not copied into the repo.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys
from unicorn import Uc, UC_ARCH_MIPS, UC_MODE_MIPS32, UC_MODE_LITTLE_ENDIAN, UC_HOOK_CODE
from unicorn.mips_const import *

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'vendor/h1-sdk'))
from h1_bda.header import decode_header

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('bda', type=Path)
    args = p.parse_args()
    data = args.bda.read_bytes(); payload = struct.unpack_from('<I', decode_header(data), 20)[0]
    uc = Uc(UC_ARCH_MIPS, UC_MODE_MIPS32 | UC_MODE_LITTLE_ENDIAN)
    uc.mem_map(0, 64 * 1024 * 1024); uc.reg_write(UC_MIPS_REG_CP0_STATUS, 0)
    def put(addr, blob): uc.mem_write(addr & 0x1fffffff, blob)
    def word(addr, value): put(addr, struct.pack('<I', value))
    def string(addr):
        buf = bytearray()
        while True:
            ch = uc.mem_read((addr + len(buf)) & 0x1fffffff, 1)[0]
            if not ch: return buf.decode('gbk')
            buf.append(ch)
            assert len(buf) < 1024
    put(0x83c00020, data[payload:])
    for slot, table in [(4, 0x80002000), (8, 0x80003000), (12, 0x80004000), (16, 0x80005000), (20, 0x80006000)]:
        word(0x83c00000 + slot, table)
    callbacks = {0x80001000: 'debug', 0x80001010: 'wallpaper_open', 0x80001020: 'file_selector'}
    for address in callbacks: put(address, struct.pack('<II', 0x03e00008, 0))
    word(0x80006000 + 0x94, 0x80001000)
    word(0x80002000 + 0x978, 0x80001010)
    word(0x80002000 + 0x9ec, 0x80001020)
    uc.reg_write(UC_MIPS_REG_SP, 0x83aff000)
    found = {}
    def callback(uc, address, size, user):
        if address == 0x80001020:
            a0, a1, a2 = [uc.reg_read(r) for r in [UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2]]
            ra, sp = uc.reg_read(UC_MIPS_REG_RA), uc.reg_read(UC_MIPS_REG_SP)
            found.update(ok=True, source_sha256=hashlib.sha256(data).hexdigest(),
                         table='GUI', api_offset='0x9ec', call_site=hex(ra - 8),
                         args=[string(a0), string(a1), 'output_path'],
                         output_relative_to_sp=a2 - sp, next_local_relative_to_sp=328,
                         reserved_output_bytes=328 - (a2 - sp),
                         kind='Original H1 BBVM MIPS startup trace with trapped services')
            uc.emu_stop()
        else: uc.reg_write(UC_MIPS_REG_V0, 0)
    uc.hook_add(UC_HOOK_CODE, callback, begin=0x80001000, end=0x8000102f)
    uc.emu_start(0x83c00020, 0, timeout=5_000_000, count=100000)
    assert found and found['args'][:2] == ['A:\\BBasic\\', 'bin'], found
    assert found['call_site'] == '0x83c01814' and found['reserved_output_bytes'] == 264
    out = ROOT / 'build/verification/bbvm-selector-trace.json'; out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(found, indent=2) + '\n')
    print(json.dumps(found, indent=2))

if __name__ == '__main__': main()
