"""Execute touch UI and full CPU/RAM snapshot restore in the built MIPS BDA."""
from pathlib import Path
import argparse,hashlib,json,re,struct,zlib
from PIL import Image
from mips_smoke import Machine,ROOT
from make_test_rom import make_rom as gba_rom
from make_gb_test_rom import make_rom as gb_rom
LOG='A:\\GBA\\h1gba.log'
def symbol(name,map_path):
    return int(re.search(r'(0x[0-9a-f]+)\s+'+re.escape(name)+r'\s*$',map_path.read_text(),re.M)[1],16)
def tap(x,y): return [(11,x,y),(8,x,y)]
def key(k): return [(9,k),(10,k)]
class Pause(Machine):
    def __init__(self,bda,kind,map_path,files=None):
        self.kind=kind;path='A:\\GBA\\PAUSE.'+kind
        super().__init__(bda,path=path,files=files or {path:gba_rom(tone=True) if kind=='gba' else gb_rom(kind=='gbc')})
        self.word(0x800026c0,0x80001900)
        self.callbacks[0x80001900]=self.coordinates
        self.write(0x80001900,struct.pack('<6I',0x27bdffa8,0xafbf0050,0,0,0x00a0b821,0x0080b021))
        self.pause_sent=False;self.idle=0;self.mutated=False;self.restored=False
        self.menu_steps=0;self.after_resume=None;self.golden=None;self.about_frame=None
        self.map_path=map_path;self.cpu_address=symbol('reg' if kind=='gba' else 'h1gb_cpu',map_path)
        self.ram_address=symbol('ewram' if kind=='gba' else 'h1gb_ram',map_path)
        if kind=='gba' and json.loads(bda.with_suffix('.build.json').read_text())['core']=='jit': self.ram_address+=0x40000
        self.actions=([(11,330,230),(8,10,10)]+tap(100,252)+tap(400,254)+key(39)+key(41)+ # About: touch/confirm/back
            tap(330,80)+tap(70,132)+key(1)+key(41)+ # drag cancels EXIT; A=Q, back
            tap(90,175)+tap(100,72)+tap(100,72)+tap(100,112)+key(41)+ # linear aspect, skip2
            tap(90,130)+tap(100,72)+key(41)+ # state slot1
            tap(330,130)+tap(100,72)+key(41)+ # load slot1
            tap(330,175)+tap(90,80)) # sound off, resume
    def coordinates(self,x,y,*args):
        position=self.read(0x80007008,4)
        self.write(x,position[:2]);self.write(y,position[2:])
        # Emulate the service return directly (its instruction shape is evidence).
        from unicorn.mips_const import UC_MIPS_REG_PC,UC_MIPS_REG_RA
        self.uc.reg_write(UC_MIPS_REG_PC,self.uc.reg_read(UC_MIPS_REG_RA))
        return 0
    def watched(self):
        if self.kind=='gba':
            sram=symbol('gamepak_backup',self.map_path)
            return [(self.ram_address,256),(sram,128),(self.cpu_address,64)]
        ram=self.ram_address
        sbank=struct.unpack('<I',self.read(ram+33024,4))[0]
        return [(ram,256),(ram+256,256),(sbank,128),(self.cpu_address,56)]
    def event(self,code,button,*args):
        log=self.files.get(LOG,b'');paused=log.rfind(b'PAUSE_MENU_BEGIN')>log.rfind(b'PAUSE_MENU_END')
        event=(-1,-1)
        if self.blits>=2 and not self.pause_sent:
            self.pause_sent=True;event=(11,0)
            self.write(0x80007008,struct.pack('<2H',330,230)) # opening touch is above EXIT
            self.actions.insert(0,(8,330,230))
        elif paused:
            assert not self.audio_active
            if b'MENU_PAGE page=5' in log and self.about_frame is None:
                self.about_frame=self.read(0x82000000,480*272*4)
            if self.idle<20:
                current=[self.read(a,n) for a,n in self.watched()]
                if not self.idle:self.frozen=current
                assert current==self.frozen, 'CPU/RAM changed while menu idle'
                self.idle+=1
            else:
                if b'STATE_SAVE slot=1 status=1' in log and not self.mutated:
                    self.golden=[self.read(a,n) for a,n in self.watched()]
                    for a,n in self.watched():self.write(a,bytes([0x55])*n)
                    self.mutated=True
                if b'STATE_LOAD slot=1 status=1' in log and not self.restored:
                    restored=[self.read(a,n) for a,n in self.watched()]
                    assert restored==self.golden, [(a,x[:12].hex(),y[:12].hex()) for (a,n),x,y in zip(self.watched(),restored,self.golden)]
                    self.restored=True
                assert self.actions,'Unexpected menu remains open'
                action=self.actions.pop(0);event=action[:2]
                if action[0] in (8,11):
                    self.write(0x80007008,struct.pack('<2H',action[1],action[2]));event=(action[0],0)
                self.menu_steps+=1
        elif self.restored:
            if self.after_resume is None:self.after_resume=self.blits
            if self.blits-self.after_resume>=3:event=(9,24)
        self.word(code,event[0]);self.word(button,event[1]);return 0
class ErrorMenu(Pause):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.actions=key(35)+key(27)+key(39)+key(27)+key(39)+key(41)+key(35)+key(27)+key(39)+key(39)+key(41)+key(41)
        self.resumed_at=None
    def event(self,code,button,*args):
        log=self.files.get(LOG,b'');paused=log.rfind(b'PAUSE_MENU_BEGIN')>log.rfind(b'PAUSE_MENU_END')
        event=(-1,-1)
        if self.blits>=2 and not self.pause_sent:self.pause_sent=True;event=(9,31)
        elif paused:
            current=[self.read(a,n) for a,n in self.watched()]
            if not self.idle:self.frozen=current
            assert current==self.frozen, 'Empty/corrupt state changed core'
            self.idle+=1
            if self.idle==2:event=(9,31) # Holding P must not immediately close the menu.
            if self.idle==3:event=(10,31)
            if self.idle>10:
                assert self.actions,'Unexpected error menu remains open'
                event=self.actions.pop(0);self.menu_steps+=1
        elif self.pause_sent:
            if self.resumed_at is None:self.resumed_at=self.blits
            if self.blits-self.resumed_at>=3:event=(9,24)
        self.word(code,event[0]);self.word(button,event[1]);return 0
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--bda',type=Path,default=ROOT/'dist/H1GBA.bda')
    parser.add_argument('--map',type=Path,default=ROOT/'build/release/H1GBA.map');args=parser.parse_args()
    results=[];out=ROOT/'build/verification';out.mkdir(exist_ok=True)
    for kind in ['gba','gb','gbc']:
        machine=Pause(args.bda,kind,args.map);seconds=machine.run()
        assert machine.restored and machine.menu_steps>30 and machine.blits>4
        assert machine.about_frame and machine.files[LOG].count(b'MENU_PAGE page=5')>=2
        path=machine.rom_path
        cfg=machine.files[path+'.cfg.s0'];assert zlib.crc32(cfg[28:])==struct.unpack_from('<I',cfg,20)[0]
        fields=struct.unpack_from('<5I',cfg,28);assert fields[2:]==(3,2,0),fields
        assert cfg[28+20+1]==9 and cfg[28+20+16]==0 and cfg[28+20+39]==0
        assert path+'.st1.s0' in machine.files
        pixels=struct.unpack('<130560I',machine.menu_frames[1]);im=Image.new('RGB',(480,272))
        im.putdata([((p>>16)&255,(p>>8)&255,p&255) for p in pixels]);im.save(out/('pause-'+kind+'.png'))
        pixels=struct.unpack('<130560I',machine.about_frame)
        im.putdata([((p>>16)&255,(p>>8)&255,p&255) for p in pixels]);im.save(out/('about-'+kind+'.png'))
        # New invocation restores configuration, releases old input, stays silent.
        second=Machine(args.bda,path=path,files=machine.files,menu=True);second.run()
        assert not second.audio_submissions
        assert b'CONFIG_LOAD status=1 enabled=1 scale=3 skip=2 sound=0' in second.files[LOG]
        damaged=dict(machine.files);state_path=path+'.st1.s0'
        blob=bytearray(damaged[state_path]);blob[100]^=1;damaged[state_path]=bytes(blob)
        errors=ErrorMenu(args.bda,kind,args.map,files=damaged);errors.run()
        assert b'STATE_LOAD slot=2 status=0' in errors.files[LOG]
        assert b'STATE_LOAD slot=1 status=-1' in errors.files[LOG]
        assert errors.files[state_path]==damaged[state_path]
        results.append({'kind':kind,'seconds':round(seconds,2),'menu_events':machine.menu_steps,
            'paused_cpu_ram_stable':True,'cpu_ram_sram_restored':True,'config_reopened':True,'blits':machine.blits})
    engine=json.loads(args.bda.with_suffix('.build.json').read_text())['core']
    report={'ok':True,'bda':str(args.bda),'sha256':hashlib.sha256(args.bda.read_bytes()).hexdigest(),
        'core':engine,'empty_corrupt_preserved':True,'P_keyboard_menu':True,'touch_drag_cancelled':True,
        'about_touch_keyboard_return':True,'results':results}
    (out/('pause-menu-'+engine+'-smoke.json')).write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
