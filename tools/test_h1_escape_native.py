"""Verify Escape bindings through real V1.41 UI and read-only guest memory.

Start at the private test image's ROM picker (AUDIO.gba, H1TEST.gba,
another GBA, GBTEST.gb, GBCTEST.gbc). No firmware services are replaced.
"""
import argparse,hashlib,json,re,subprocess,sys,time
from pathlib import Path
from test_h1_gb_native import get,post,key,tap,memory
ROOT=Path(__file__).resolve().parents[1]

def touch(x,y):
    # Give real ADC polling time to observe each press on a loaded host.
    post('/api/touch',{'x':x,'y':y,'down':True});time.sleep(.6)
    post('/api/touch',{'x':x,'y':y,'down':False});time.sleep(.7)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work-dir',type=Path,required=True)
    parser.add_argument('--bda',type=Path,default=ROOT/'dist/H1GBA.bda')
    parser.add_argument('--map',type=Path,default=ROOT/'build/release/H1GBA.map')
    parser.add_argument('--prefix',required=True)
    parser.add_argument('--date',required=True,help='Validation date in the operator timezone')
    args=parser.parse_args();work=args.work_dir.resolve();out=work/'evidence';out.mkdir(exist_ok=True)
    text=args.map.read_text(encoding='utf-8')
    def symbol(name):
        return int(re.search(r'(0x[0-9a-f]+)\s+'+re.escape(name)+r'\s*$',text,re.M)[1],16)
    frame_address=int(re.search(r'\.bss\.total_frames\s+(0x[0-9a-f]+)',text)[1],16)
    layout=re.search(r'\.bss\.input\s+(0x[0-9a-f]+)\s+(0x[0-9a-f]+)',text)
    assert layout and int(layout[2],16)==128
    input_address=int(layout[1],16)
    # input_state in frontend.h: held[45], mapping[45], ready, pause, mask, exit.
    def word(a):return memory(a,1)[0]
    def byte(a):return (word(a&~3)>>((a&3)*8))&255
    def frames():return word(frame_address)
    def mapping():return byte(input_address+45+24)
    def mask():return word(input_address+100)&65535
    def running():
        assert word(input_address+96)==0 and word(input_address+104)==0
        assert word(input_address+108)==0
    def advance(before):
        deadline=time.monotonic()+12
        while time.monotonic()<deadline:
            if frames()>before+4:return frames()
            time.sleep(.2)
        raise AssertionError('No game progress after Escape or resume')
    def resume(before):
        # A missed ADC press leaves the menu open. Retry only while its pause
        # flag is still set; never inject another touch into a resumed game.
        for _ in range(2):
            touch(90,80)
            deadline=time.monotonic()+3
            while time.monotonic()<deadline:
                if frames()>before+4:running();return
                time.sleep(.2)
            if word(input_address+96)==0:advance(before);running();return
        raise AssertionError('Continue button did not resume game')
    def screenshot(name):
        path=out/(args.prefix+'-'+name+'.png')
        subprocess.run([sys.executable,ROOT/'vendor/h1-sdk/scripts/capture_emulator_frame.py',path],check=True)
        return hashlib.sha256(path.read_bytes()).hexdigest()
    def core_a(kind):
        if kind=='gba':return word(symbol('io_registers')+0x130)&65535
        ram=word(symbol('h1gb_ram')+33024)
        assert 0x80000000<=ram<0x83c00000
        return (word(ram)>>8)&255
    def press_and_release(kind):
        before=frames();key(24)
        try:
            held=advance(before);running();assert mask()&(1<<8)
            a=core_a(kind)
            if kind=='gba':assert a&1==0
            else:assert a==0xa5
        finally:key(24,False)
        released=advance(held);running();assert not mask()&(1<<8)
        b=core_a(kind)
        if kind=='gba':assert b&1==1
        else:assert b==0x11
        return {'frames_before':before,'frames_held':held,'frames_released':released,
                'core_A_held':a,'core_A_released':b}
    status=get('/api/status');assert status['running']
    assert Path(status['nand']).resolve()==work/'h1-system.raw'
    report={'ok':False,'date':args.date,'environment':'Full H1 V1.41 firmware in QEMU',
        'physical_hardware_tested':False,'bda_sha256':hashlib.sha256(args.bda.read_bytes()).hexdigest(),
        'kernel_sha256':hashlib.sha256(Path(status['kernel']).read_bytes()).hexdigest(),
        'qemu_sha256':hashlib.sha256(Path(status['qemu']).read_bytes()).hexdigest(),
        'original_system_volume':word(0x8095f350),'runs':[]}
    target=out/(args.prefix+'-native.json')
    def save():target.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    for kind,row in [('gba',0),('gb',3),('gbc',4)]:
        for _ in range(row):tap(27)
        tap(39);time.sleep(5);assert frames()>4 and mapping()==0;running()
        before=frames();key(24)
        try:
            unmapped_frames=advance(before);running();assert mask()==0
        finally:key(24,False)
        touch(100,100);frozen=frames();touch(330,80);touch(70,132)
        # The firmware can finish drawing the capture prompt after touch-up.
        # Retry only while the requested binding has not been observed.
        for _ in range(3):
            tap(24)
            if mapping()==9:break
        assert mapping()==9 and frames()==frozen
        shot=screenshot(kind+'-escape-mapping')
        tap(41);resume(frozen)
        result={'kind':kind,'unmapped_Escape_frames':unmapped_frames-before,
                'mapping_Escape':mapping(),'mapping_screenshot_sha256':shot,
                'gameplay':press_and_release(kind)}
        if kind=='gba':
            path=out/(args.prefix+'-gba-audio.wav')
            subprocess.run([sys.executable,ROOT/'tools/capture_h1_audio.py',path,'--seconds','3'],check=True)
            result['audio']=json.loads(path.with_suffix('.json').read_text(encoding='utf-8'))
            assert result['audio']['nonzero_samples']>1000
        touch(100,100);frozen=frames();tap(24);time.sleep(.3)
        assert frames()==frozen and word(input_address+96)==1 and word(input_address+104)==0
        result['Escape_does_not_close_pause_menu']=True
        resume(frozen)
        tap(31);frozen=frames();time.sleep(.4);assert frames()==frozen
        result['P_opens_pause_menu']=True
        resume(frozen)
        touch(100,100);touch(100,212);time.sleep(2) # Change game, return to native picker.
        result['system_volume_restored']=word(0x8095f350)
        assert result['system_volume_restored']==report['original_system_volume']
        report['runs'].append(result);save()
    tap(39);time.sleep(5);assert mapping()==9;running()
    restored={'kind':'gba-reopen','mapping_Escape':mapping(),'gameplay':press_and_release('gba')}
    touch(100,100);touch(330,212);time.sleep(3) # Explicit pause-menu Exit game.
    restored['system_volume_restored']=word(0x8095f350)
    assert restored['system_volume_restored']==report['original_system_volume']
    report['runs'].append(restored)
    report['desktop_screenshot_sha256']=screenshot('menu-exit-desktop')
    stopped=post('/api/stop',{})
    assert not stopped['running'] and stopped['returncode']==0 and stopped['last_error'] is None
    report['status']={k:stopped[k] for k in ('running','returncode','last_error')}
    report['ok']=True;save();print(json.dumps(report,indent=2))

if __name__=='__main__':main()
