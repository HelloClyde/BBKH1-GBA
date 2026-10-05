"""Execute the combined H1 MIPS BDA with original GB/GBC cartridges."""
import hashlib
import json
import struct
import zlib
from pathlib import Path
from PIL import Image
from mips_smoke import Machine, ROOT
from make_gb_test_rom import make_rom
from make_test_rom import make_rom as gba_rom

LOG = 'A:\\GBA\\h1gba.log'

def slot_data(machine, path):
    slots = [v for k,v in machine.files.items() if k in (path+'.s0',path+'.s1')]
    slot = max(slots, key=lambda v: struct.unpack_from('<I',v,12)[0])
    assert zlib.crc32(slot[28:]) == struct.unpack_from('<I',slot,20)[0]
    assert zlib.crc32(slot[:24]) == struct.unpack_from('<I',slot,24)[0]
    return slot[28:]

def screenshot(machine, dest):
    pixels = struct.unpack('<130560H',machine.screen)
    image=Image.new('RGB',(480,272))
    image.putdata([((p>>11)*255//31,((p>>5)&63)*255//63,(p&31)*255//31) for p in pixels])
    image.save(dest)
    assert set(pixels[:89]) == {0} and set(pixels[391:480]) == {0}
    assert len(set(pixels)) == 5
    return sorted(set(pixels))

class Switch(Machine):
    def __init__(self,bda):
        self.paths=['A:\\GBA\\one.gba','A:\\GBA\\two.gb','A:\\GBA\\three.gbc','A:\\GBA\\four.gba']
        files={p:gba_rom(tone=True) if p.endswith('.gba') else make_rom(p.endswith('.gbc')) for p in self.paths}
        super().__init__(bda,files=files,path=self.paths[0])
        self.chosen=0; self.start_blits=0; self.exit_sent=False
    def select_file(self,*args):
        self.rom_path=self.paths[self.chosen]; self.chosen+=1; self.start_blits=self.blits; self.exit_sent=False
        return super().select_file(*args)
    def event(self,code,key,*args):
        if self.blits-self.start_blits>=10 and not self.exit_sent:
            self.exit_sent=True; self.events.append((9,24 if self.chosen==4 else 36))
        event=self.events.pop(0) if self.events else (-1,-1)
        self.word(code,event[0]); self.word(key,event[1]);return 0

class BadRom(Machine):
    def select_file(self,*args):
        if self.select_calls: self.rom_path=None
        return super().select_file(*args)
    def message(self,*args): return 0

def main():
    bda=ROOT/'build/test-20/H1GBA.bda'; out=ROOT/'build/verification';out.mkdir(exist_ok=True)
    results={}
    for color in [False,True]:
        kind='gbc' if color else 'gb'; path='A:\\GBA\\TEST.'+kind
        first=Machine(bda,files={path:make_rom(color)},path=path,press_a=True); first.run()
        data=slot_data(first,path)
        assert data[:4]==bytes.fromhex('5aa5ef42') and data[5]==0
        colors=screenshot(first,out/(kind+'-smoke.png'))
        if color: assert colors==[0,31,2016,63488,65535],colors
        assert first.audio_submissions and any(int.from_bytes(x,'little',signed=True) for x in first.audio_observed)
        second=Machine(bda,files=first.files,path=path);second.run(); restored=slot_data(second,path)
        assert restored[1]==0x11 and restored[5]==0xc0
        assert 'SAVE restored' in second.files[LOG].decode('gbk')
        changed=bytearray(make_rom(color));changed[0x134]=ord('X')
        replacement=BadRom(bda,files={**second.files,path:bytes(changed)},path=path);replacement.run()
        assert 'SAVE_LOAD_END status=-1' in replacement.files[LOG].decode('gbk')
        assert {k:v for k,v in replacement.files.items() if k.endswith(('.s0','.s1'))}=={k:v for k,v in second.files.items() if k.endswith(('.s0','.s1'))}
        if color:
            assert data[8192:8196]==b'RTC1'
            assert struct.unpack_from('<I',restored,8192+28)[0]>struct.unpack_from('<I',data,8192+28)[0]
        results[kind]={'colors':colors,'sram_bytes':len(data),'blits':first.blits,'audio_samples':len(first.audio_observed),'restored':True}
    no_battery='A:\\GBA\\NOBATT.gb'
    m=Machine(bda,files={no_battery:make_rom(battery=False)},path=no_battery);m.run()
    assert not any(k.endswith(('.s0','.s1')) for k in m.files)
    for mapper in [6,9,0x1b]:
        p='A:\\GBA\\MAPPER%d.gb'%mapper
        m=Machine(bda,files={p:make_rom(mapper=mapper)},path=p);m.run();data=slot_data(m,p)
        assert data[0]==(10 if mapper==6 else 0x5a)
        assert data[3]==(2 if mapper==6 else 0 if mapper==9 else 0x42)
        assert len(data)==(512 if mapper==6 else 8192)
        if mapper==6: assert data[6:8]==b'\x0d\x0d'
    p='A:\\GBA\\SMALL.gb'
    m=Machine(bda,files={p:make_rom(ram_code=1)},path=p);m.run();data=slot_data(m,p)
    assert len(data)==2048 and data[6:8]==b'\xbd\xbd'
    p='A:\\GBA\\RTC.gbc'
    m=Machine(bda,files={p:make_rom(True,rtc_probe=True)},path=p);m.run();data=slot_data(m,p)
    assert data[4]==0x41
    assert struct.unpack_from('<8I',data,8192)==(0x31435452,58,59,23,511,1,0,70224)
    for content in [bytes(512),make_rom()[:32768],make_rom(mapper=0x22)]:
        p='A:\\GBA\\INVALID.gb';m=BadRom(bda,files={p:content},path=p);m.run()
        assert 'GB_LOAD_FAILED' in m.files[LOG].decode('gbk')
    switch=Switch(ROOT/'dist/H1GBA.bda');switch.run()
    log=switch.files[LOG].decode('gbk')
    assert log.count('GUI_CONTEXT_CLOSE_END')==4 and log.count('AUDIO_CLOSE_END descriptors=1')==4
    assert log.count('JIT_STATE enabled=1')==2 and log.count('JIT_FREE_END')==2
    assert log.count('GB_LOAD mode=')==2
    results['cross_core_switch']={'order':['GBA JIT','GB','GBC','GBA JIT'],'ok':True}
    report={'ok':True,'kind':'Actual MIPS combined BDA, mocked H1 firmware services','sha256':hashlib.sha256(bda.read_bytes()).hexdigest(),'results':results,'bad_roms_rejected':3,'no_battery_no_save':True,'changed_cartridge_save_preserved':True,'small_SRAM_and_MBC2_mirroring':True,'MBC3_RTC_day_bit_and_stop':True}
    (out/'gb-smoke.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
