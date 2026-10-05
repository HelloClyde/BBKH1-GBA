"""Original SM83 diagnostic cartridges: graphics, PCM, keys, SRAM and banking."""
from pathlib import Path
import argparse

def make_rom(cgb=False, mapper=None, battery=True, rtc_probe=False, ram_code=2):
    rom = bytearray(65536)
    rom[0x100:0x104] = bytes([0xc3, 0x50, 0x01, 0])
    rom[0x134:0x140] = b'H1 GBC TEST\0' if cgb else b'H1 GB TEST\0\0'
    rom[0x143] = 0xc0 if cgb else 0
    rom[0x147] = mapper if mapper is not None else (0x10 if cgb else 3) if battery else 1
    rom[0x148] = 1
    rom[0x149] = ram_code if battery else 0
    code = bytearray(); labels = {}; fixups = []
    def emit(*values): code.extend(values)
    def label(name): labels[name] = 0x150 + len(code)
    def jp(name, op=0xc3): emit(op, 0, 0); fixups.append((len(code)-2, name))
    def store(address, value): emit(0x3e, value, 0xea, address & 255, address >> 8)
    emit(0xf3, 0x31, 0xfe, 0xff)
    label('vblank'); emit(0xf0, 0x44, 0xfe, 144); jp('vblank', 0xda)
    store(0xff40, 0); store(0x0000, 0x0a)
    mbc2 = rom[0x147] in (5,6)
    emit(0xfa, 0x00, 0xa0, 0xfe, 0xfa if mbc2 else 0x5a, 0x3e, 0)
    jp('fresh', 0xc2); emit(0x3e, 0xc0)
    label('fresh'); emit(0xea, 0x05, 0xa0)
    store(0xa000, 0x5a)
    store(0x2100 if mbc2 else 0x2000, 2); emit(0xfa, 0x00, 0x40, 0xea, 0x03, 0xa0); store(0x2100 if mbc2 else 0x2000, 1)
    if rtc_probe:
        for reg,value in [(8,58),(9,59),(10,23),(11,255),(12,0x41)]:
            store(0x4000,reg);store(0xa000,value)
        store(0x6000,0);store(0x6000,1);store(0x4000,12)
        emit(0xfa,0,0xa0,0x57);store(0x4000,0);emit(0x7a,0xea,4,0xa0)
    if mbc2 or ram_code == 1:
        store(0xa206 if mbc2 else 0xa806,0xbd)
        emit(0xfa,6,0xa0,0xea,7,0xa0)
    # Four tiles with constant color numbers 0,1,2,3, repeating across the map.
    emit(0x21, 0, 0x80, 0x06, 8)
    label('tile0'); emit(0xaf, 0x22, 0x22, 0x05); jp('tile0', 0xc2)
    for color in [1,2,3]:
        emit(0x06, 8); label('tile'+str(color))
        emit(0x3e, 255 if color & 1 else 0, 0x22, 0x3e, 255 if color & 2 else 0, 0x22, 0x05)
        jp('tile'+str(color), 0xc2)
    emit(0x21, 0, 0x98, 0x01, 0, 4, 0x16, 0)
    label('map'); emit(0x7a, 0x22, 0x14, 0x7a, 0xe6, 3, 0x57, 0x0b, 0x78, 0xb1); jp('map', 0xc2)
    store(0xff47, 0xe4)
    if cgb:
        store(0xff68, 0x80)
        for value in [0xff,0x7f, 0x1f,0, 0xe0,3, 0,0x7c]: store(0xff69, value)
        store(0xff4d, 1); emit(0x10, 0)  # CGB double-speed CPU
    for address, value in [(0xff26,0x80),(0xff24,0x77),(0xff25,0x11),
                           (0xff11,0x80),(0xff12,0xf0),(0xff13,0xd6),(0xff14,0x86),(0xff40,0x91)]:
        store(address,value)
    label('loop'); store(0xff00, 0x10); emit(0xf0, 0, 0xe6, 1, 0x3e, 0x11)
    jp('released', 0xc2); emit(0x3e,0xa5)
    label('released'); emit(0xea, 1, 0xa0)
    store(0xff00,0x20); emit(0xf0,0,0xea,2,0xa0)
    jp('loop')
    for offset, name in fixups:
        code[offset:offset+2] = labels[name].to_bytes(2,'little')
    rom[0x150:0x150+len(code)] = code
    rom[0x8000] = 0x42
    checksum = 0
    for value in rom[0x134:0x14d]: checksum = (checksum-value-1)&255
    rom[0x14d] = checksum
    total = sum(rom)&65535; rom[0x14e:0x150] = total.to_bytes(2,'big')
    return bytes(rom)

if __name__ == '__main__':
    p=argparse.ArgumentParser(); p.add_argument('output',type=Path); p.add_argument('--cgb',action='store_true'); a=p.parse_args()
    a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_bytes(make_rom(a.cgb))
