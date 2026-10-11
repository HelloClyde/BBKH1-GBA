"""Verify volume in V1.41 firmware, starting at the private ROM picker.

Only emulator input APIs and read-only debug memory are used. Requires AUDIO.gba,
GBTEST.gb and GBCTEST.gbc in the known grouped picker order.
"""
import argparse,hashlib,json,re,subprocess,sys,time
from pathlib import Path
from test_h1_gb_native import get,post,tap,memory
ROOT=Path(__file__).resolve().parents[1]
VOLUME=0x8095f350

def touch(x,y):
    post('/api/touch',{'x':x,'y':y,'down':True});time.sleep(.25)
    post('/api/touch',{'x':x,'y':y,'down':False});time.sleep(.6)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work-dir',type=Path,required=True)
    parser.add_argument('--initial-gba-volume',type=int,choices=(70,100),default=100)
    parser.add_argument('--bda',type=Path,default=ROOT/'dist/H1GBA.bda')
    parser.add_argument('--map',type=Path,default=ROOT/'build/release/H1GBA.map')
    parser.add_argument('--prefix',default='volume')
    args=parser.parse_args()
    work=args.work_dir.resolve();out=work/'evidence';out.mkdir(exist_ok=True)
    map_text=args.map.read_text()
    frame_address=int(re.search(r'\.bss\.total_frames\s+(0x[0-9a-f]+)',map_text)[1],16)
    def frames():return memory(frame_address,1)[0]
    def wait_advance(previous):
        deadline=time.monotonic()+12
        while time.monotonic()<deadline:
            current=frames()
            if current>previous+4:return current
            time.sleep(.3)
        raise AssertionError('Game did not advance after resume')
    def shot(name):
        target=out/(args.prefix+'-'+name+'.png')
        subprocess.run([sys.executable,ROOT/'vendor/h1-sdk/scripts/capture_emulator_frame.py',target],check=True)
        return str(target)
    def record(name):
        target=out/(args.prefix+'-'+name+'.wav')
        subprocess.run([sys.executable,ROOT/'tools/capture_h1_audio.py',target,'--seconds','3'],check=True)
        return json.loads(target.with_suffix('.json').read_text())
    original=memory(VOLUME,1)[0]
    report={'environment':'Full H1 V1.41 firmware in QEMU','physical_hardware_tested':False,
            'bda_sha256':hashlib.sha256(args.bda.read_bytes()).hexdigest(),
            'original_system_volume':original,'runs':[]}
    for kind,row in [('gba',0),('gb',3),('gbc',4),('gba-reopen',0)]:
        for _ in range(row):tap(27)
        tap(39);time.sleep(8);assert frames()>4
        expected=0 if kind=='gba-reopen' else args.initial_gba_volume if kind=='gba' else 100
        assert memory(VOLUME,1)[0]==expected,(kind,memory(VOLUME,1))
        result={'kind':kind,'loaded_volume':expected}
        if kind!='gba-reopen':
            touch(100,100);time.sleep(.5);before=frames()
            touch(330,175)
            for _ in range((expected-70)//10):tap(40)
            assert memory(VOLUME,1)[0]==70 and frames()==before
            result['menu_screenshot']=shot(kind+'-70-menu')
            tap(41);touch(100,80);result['resumed_frames']=wait_advance(before)
            assert memory(VOLUME,1)[0]==70
            if kind=='gba':
                result['audio_70']=record('gba-70')
                touch(100,100);touch(330,175)
                for _ in range(7):tap(40)
                assert memory(VOLUME,1)[0]==0
                before=frames();tap(41);touch(100,80);wait_advance(before)
                result['audio_0']=record('gba-0')
                assert memory(VOLUME,1)[0]==0
        tap(36);time.sleep(4)
        assert memory(VOLUME,1)[0]==original
        result['system_volume_restored']=memory(VOLUME,1)[0]
        report['runs'].append(result)
        (out/(args.prefix+'-native.json')).write_text(json.dumps(report,indent=2)+'\n')
    tap(24);time.sleep(3);report['desktop_screenshot']=shot('exit')
    report['ok']=True
    report['status']=post('/api/stop',{})
    assert not report['status']['running'] and report['status']['returncode']==0 and not report['status']['last_error']
    (out/(args.prefix+'-native.json')).write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
