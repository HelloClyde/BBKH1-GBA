"""Exercise actual ARM serial RTC I/O through the compiled MIPS frontend/core."""
import datetime
import argparse
import hashlib
import json
import re
import struct
from unicorn.mips_const import UC_MIPS_REG_RA, UC_MIPS_REG_V0
from mips_smoke import Machine as BaseMachine, ROOT
from make_rtc_test_rom import make_rtc_rom

ROM='A:\\GBA\\RTCTEST.gba'
class Machine(BaseMachine):
    def __init__(self,*args,**kwargs):
        kwargs['menu']=True  # Exercise Escape exit with unbounded release packages too.
        super().__init__(*args,**kwargs)
class ClockWarning(Machine):
    def message(self,parent,text,title,flags,*args):
        self.warning = self.string(text)
        return 0
def payload(machine,suffix=''):
    values=[]
    for slot in (0,1):
        data=machine.files.get(ROM+suffix+'.s'+str(slot))
        if data:
            header=struct.unpack('<7I',data[:28]); values.append((header[3],data[28:]))
    assert values, suffix
    return max(values)[1]
def expected(seconds):
    d=datetime.datetime.fromtimestamp(seconds,datetime.timezone.utc)
    bcd=lambda n:(n//10)*16+n%10
    return bytes(bcd(v) for v in (d.year%100,d.month,d.day,(d.weekday()+1)%7,d.hour,d.minute,d.second))
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bda',type=type(ROOT),default=ROOT/'build/test-20/H1GBA.bda')
    bda=parser.parse_args().bda
    host=1791199800
    first=Machine(bda,files={ROM:make_rtc_rom()},path=ROM)
    first.word(0xb0003004,host);first.run()
    sram=payload(first)
    assert sram[0]==0x40 and sram[1:8]==expected(host),sram[:34].hex()
    assert sram[8:10]==b'\0\x40',sram[:34].hex()
    assert sram[10:17]==bytes.fromhex('26022806235958'),sram[:34].hex()
    assert sram[17:24]==bytes.fromhex('26022806010203'),sram[:34].hex()
    assert sram[24:27]==bytes.fromhex('810203'),sram[:34].hex()
    assert sram[27:34]==bytes.fromhex('26022806130203'),sram[:34].hex()
    rtc=struct.unpack('<8I',payload(first,'.rtc'))
    assert rtc[:2]==(0x31435452,1) and rtc[4]==0x40,rtc
    second=Machine(bda,files={**first.files,ROM:make_rtc_rom(probe=True)},path=ROM)
    second.word(0xb0003004,host+120);second.run()
    sram2=payload(second)
    assert sram2[1:8]==expected(rtc[2]+120),sram2[:8].hex()
    assert b'RTC_RESTORE' in second.files['A:\\GBA\\h1gba.log']
    # Moving the H1 calendar backwards between sessions must not rewind RTC.
    third=Machine(bda,files={**first.files,ROM:make_rtc_rom(probe=True)},path=ROM)
    third.word(0xb0003004,host-120);third.run()
    assert payload(third)[1:8]==expected(rtc[2])
    # Existing SRAM remains independently loadable; older versions have no RTC sidecar.
    legacy={k:v for k,v in first.files.items() if '.rtc.s' not in k}
    old=Machine(bda,files={**legacy,ROM:make_rtc_rom(probe=True)},path=ROM);old.word(0xb0003004,host);old.run()
    assert payload(old)[1:8]==expected(host)
    # A disabled/unset hardware clock uses the wrap-safe 80 Hz fallback.
    fallback=Machine(bda,files={ROM:make_rtc_rom(probe=True)},path=ROM)
    fallback.word(0xb0003000,0);fallback.run()
    assert payload(fallback)[1:4]==bytes.fromhex('000101')
    damaged={**first.files,ROM:make_rtc_rom(probe=True)}
    for key in list(damaged):
        if '.rtc.s' in key: damaged[key]=damaged[key][:29]+bytes([damaged[key][29]^1])+damaged[key][30:]
    corrupt=ClockWarning(bda,files=damaged,path=ROM);corrupt.word(0xb0003004,host);corrupt.run()
    assert 'RTC state cannot be restored' in corrupt.warning
    assert all(corrupt.files[k]==v for k,v in damaged.items() if '.rtc.s' in k)
    assert payload(corrupt)[1:8]==expected(host)  # SRAM continues to save.
    # Ordinary non-RTC cartridges must not gain sidecars.
    from make_test_rom import make_rom
    plain=Machine(bda,files={ROM:make_rom()},path=ROM);plain.run()
    assert not any('.rtc.s' in k for k in plain.files)
    # Directly exercise a clock correction while this same cartridge is running.
    folder='release-interpreter' if 'interpreter' in bda.name else 'release' if bda.parent.name=='dist' else bda.parent.name
    map_text=(ROOT/'build'/folder/'H1GBA.map').read_text()
    direct=Machine(bda,path=None)
    def call(name):
        address=int(re.search(r'(0x[0-9a-f]+)\s+'+name+r'\b',map_text)[1],16)
        direct.finished=False;direct.uc.reg_write(UC_MIPS_REG_RA,0x80001ff0)
        direct.uc.emu_start(address,0,timeout=5_000_000,count=1_000_000)
        assert direct.finished
        return direct.uc.reg_read(UC_MIPS_REG_V0)
    direct.word(0xb0003004,host);call('h1_gba_rtc_begin')
    direct.word(0xb0003004,host+100);assert call('h1_gba_rtc_now')==host+100
    direct.word(0xb0003004,host+90);assert call('h1_gba_rtc_now')==host+100
    direct.word(0xb0003004,host+95);assert call('h1_gba_rtc_now')==host+105
    out=ROOT/'build/verification/rtc-smoke.json'
    out.write_text(json.dumps({'pass':True,'build_sha256':hashlib.sha256(bda.read_bytes()).hexdigest(),
        'initial':sram[:34].hex(),'restored':sram2[:8].hex(),'state':rtc,
        'checks':['GPIO status/reset/LSB command','date/time writes','12/24 hour BCD','offline +120s',
                  'clock moved backwards','legacy SRAM','unset clock fallback','corrupt RTC preserved; SRAM saves',
                  'non-RTC cartridge has no sidecar','running clock correction remains monotonic']},indent=2)+'\n')
    print('PASS GBA RTC GPIO, BCD, writes, offline catch-up, backwards clock, legacy saves and fallback')
if __name__=='__main__':main()
