"""Run native volume controls, per-ROM persistence and v1 migration in MIPS."""
import hashlib,json,struct,zlib
from PIL import Image
from mips_smoke import Machine,ROOT
from pause_menu_smoke import Pause,key,tap,LOG

class Volume(Pause):
    def __init__(self,bda,kind):
        super().__init__(bda,kind,ROOT/'build/release/H1GBA.map')
        boundary=key(40)*22+key(35)*22 if kind=='gba' else []
        self.actions=tap(330,175)+boundary+tap(120,112)*14+key(40)+key(35)+key(41)+tap(90,80)
        self.volume_frame=None;self.resumed_volume=None
    def event(self,code,button,*args):
        log=self.files.get(LOG,b'');paused=log.rfind(b'PAUSE_MENU_BEGIN')>log.rfind(b'PAUSE_MENU_END')
        event=(-1,-1)
        if self.blits>=2 and not self.pause_sent:
            self.pause_sent=True;event=(9,31);self.actions.insert(0,(10,31))
        elif paused:
            assert not self.audio_active
            if self.system_volume==30 and log.rfind(b'MENU_PAGE page=6')>log.rfind(b'MENU_PAGE page=0'):
                self.volume_frame=self.read(0x82000000,480*272*4)
            assert self.actions,'Unexpected menu remains open'
            action=self.actions.pop(0);event=action[:2]
            if action[0] in (8,11):
                self.write(0x80007008,struct.pack('<2H',action[1],action[2]));event=(action[0],0)
        elif b'PAUSE_MENU_END action=0' in log:
            if self.after_resume is None:
                self.after_resume=self.blits;self.resumed_volume=self.system_volume
            if self.blits-self.after_resume>=6:event=(9,41)
        self.word(code,event[0]);self.word(button,event[1]);return 0

def config_blob(data,version,volume):
    blob=bytearray(data);struct.pack_into('<I',blob,32,version);blob[28+65]=volume
    struct.pack_into('<I',blob,20,zlib.crc32(blob[28:]))
    struct.pack_into('<I',blob,24,zlib.crc32(blob[:24]));return bytes(blob)

def main():
    bda=ROOT/'dist/H1GBA.bda';out=ROOT/'build/verification';out.mkdir(exist_ok=True)
    results=[]
    for kind in ('gba','gb','gbc'):
        m=Volume(bda,kind);m.run();path=m.rom_path;cfg=path+'.cfg.s0'
        assert m.resumed_volume==30 and m.system_volume==37
        # Touch and keyboard use 5% steps; only the final system restore is exempt.
        assert all(abs(a-b) in (0,5) for a,b in zip(m.volume_changes[:-2],m.volume_changes[1:-1]))
        assert struct.unpack_from('<I',m.files[cfg],32)[0]==2 and m.files[cfg][28+65]==30
        assert m.files[LOG].count(b'AUDIO_OPEN_END ready=1')==1 # pause did not reopen
        if kind=='gba': assert 0 in m.volume_changes and 100 in m.volume_changes
        second=Machine(bda,files=m.files,path=path,menu=True);second.run()
        assert second.volume_changes==[30,37] and b'sound=1 volume=30' in second.files[LOG]
        # The same payload length accepts old configs and preserves all fields.
        old=dict(m.files);old[cfg]=config_blob(old[cfg],1,0)
        legacy=Machine(bda,files=old,path=path,menu=True);legacy.run()
        assert b'CONFIG_LOAD status=1 enabled=1' in legacy.files[LOG]
        assert b'sound=1 volume=100' in legacy.files[LOG] and legacy.volume_changes==[100,37]
        if kind=='gba':
            assert m.volume_frame
            image=Image.new('RGB',(480,272));pixels=struct.unpack('<130560I',m.volume_frame)
            image.putdata([((p>>16)&255,(p>>8)&255,p&255) for p in pixels]);image.save(out/'volume-menu.png')
            damaged=dict(m.files);damaged[cfg]=config_blob(damaged[cfg],2,101)
            invalid=Machine(bda,files=damaged,path=path,menu=True);invalid.run()
            assert b'CONFIG_LOAD status=1 enabled=0' in invalid.files[LOG] and invalid.files[cfg]==damaged[cfg]
            unavailable=Machine(bda,files=m.files,path=path,menu=True)
            unavailable.word(0x80001a00,0);unavailable.run()
            assert not unavailable.volume_changes and unavailable.audio_submissions
            assert b'AUDIO_VOLUME unavailable=1' in unavailable.files[LOG]
        results.append({'kind':kind,'touch_keyboard':True,'saved_volume':30,'reopened':True,
                        'v1_migrated':True,'original_system_volume_restored':37})
    report={'ok':True,'kind':'MIPS BDA with mocked firmware volume services',
            'sha256':hashlib.sha256(bda.read_bytes()).hexdigest(),'bounds_clamped':True,
            'invalid_config_preserved':True,'unsupported_volume_audio_kept':True,'results':results}
    (out/'volume-smoke.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__':main()
