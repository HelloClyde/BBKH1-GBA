"""Original ARM GPIO RTC cartridge; no commercial code or graphics."""
import struct
from pathlib import Path
from make_test_rom import make_rom

def make_rtc_rom(probe=False):
    rom = bytearray(make_rom())
    words = []
    def emit(x): words.append(x)
    def ldr(r, value): emit(0xe59f0000 | r << 12); emit(0xea000000); emit(value)
    def write(v): emit(0xe3a01000 | v); emit(0xe1c010b0)
    def direction(v): emit(0xe3a01000 | v); emit(0xe1c310b0)
    def start(command, lsb=False):
        direction(7); write(1); write(5)
        for i in (range(8) if lsb else range(7,-1,-1)):
            value = 4 | ((command >> i & 1) << 1)
            write(value); write(value | 1)
    def input_bytes(command, data, lsb=False):
        start(command, lsb)
        for byte in data:
            for i in range(8):
                value = 4 | ((byte >> i & 1) << 1)
                write(value); write(value | 1)
        write(1)
    def output(command, count, offset, lsb=False):
        start(command, lsb); direction(5)
        for byte in range(count):
            emit(0xe3a06000)
            for bit in range(8):
                write(4); write(5); emit(0xe1d010b0)
                emit(0xe2011002); emit(0xe1a010a1)  # and 2, lsr 1
                emit(0xe1866001 | (bit << 7))
            emit(0xe5c26000 | (offset + byte))
        write(1)
    ldr(0, 0x080000c4); ldr(3, 0x080000c6); ldr(2, 0x0e000000)
    emit(0xe3a01001); emit(0xe1c010b4)  # GPIO read enable
    output(0x63,1,0); output(0x65,7,1)
    if not probe:
        input_bytes(0x60,[]); output(0x63,1,8)
        input_bytes(0x62,[0x40],True); output(0x63,1,9,True)
        input_bytes(0x64,[0x26,0x02,0x28,6,0x23,0x59,0x58])
        output(0x65,7,10)
        input_bytes(0x66,[0x01,0x02,0x03]); output(0x65,7,17)
        input_bytes(0x62,[0]); input_bytes(0x66,[0x81,0x02,0x03])
        output(0x67,3,24)
        input_bytes(0x62,[0x40]); output(0x65,7,27)
    # Visible green and an infinite loop after the probe has finished.
    ldr(0,0x04000000); ldr(1,0x403); emit(0xe1c010b0)
    ldr(0,0x06000000); ldr(1,0x03e0); ldr(2,240*160)
    emit(0xe0c010b2); emit(0xe2522001); emit(0x1afffffc); emit(0xeafffffe)
    struct.pack_into('<I',rom,0,0xea0000fe)  # Entry 0x400, away from GPIO header.
    rom[0xa0:0xac] = b'H1 RTC TEST '
    rom[0xac:0xb0] = b'U33J'  # Use a known RTC hardware profile, original payload.
    rom[0xbd] = (-sum(rom[0xa0:0xbd])-0x19)&255
    payload=struct.pack('<%dI'%len(words),*words)
    rom[0x400:0x400+len(payload)] = payload
    return bytes(rom)

if __name__ == '__main__':
    target=Path(__file__).resolve().parents[1]/'build/test-rom/RTCTEST.gba'
    target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(make_rtc_rom());print(target)
