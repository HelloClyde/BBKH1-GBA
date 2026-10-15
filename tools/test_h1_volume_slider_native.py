"""Test the volume slider in full V1.41 firmware, starting at the ROM picker.

The private image must have AUDIO.gba first. Input uses the real GUI; debug
memory is read-only. Firmware, NAND and test ROMs are not distributed.
"""
import argparse,hashlib,json,re,subprocess,sys,time
from pathlib import Path
from test_h1_gb_native import get,post,tap,memory
from test_h1_escape_native import touch
ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work-dir',type=Path,required=True)
    parser.add_argument('--bda',type=Path,required=True)
    parser.add_argument('--map',type=Path,required=True)
    parser.add_argument('--prefix',required=True)
    parser.add_argument('--date',required=True)
    args=parser.parse_args();work=args.work_dir.resolve();out=work/'evidence'
    out.mkdir(exist_ok=True)
    text=args.map.read_text(encoding='utf-8')
    frame=int(re.search(r'\.bss\.total_frames\s+(0x[0-9a-f]+)',text)[1],16)
    def frames():return memory(frame,1)[0]
    def volume():return memory(0x8095f350,1)[0]
    def wait_volume(expected):
        end=time.monotonic()+5
        while time.monotonic()<end:
            if volume()==expected:return
            time.sleep(.1)
        raise AssertionError((expected,volume()))
    status=get('/api/status')
    assert status['running'] and Path(status['nand']).resolve()==work/'h1-system.raw'
    original=volume();tap(39);time.sleep(6);assert frames()>4
    touch(100,100);frozen=frames();touch(330,175)
    touch(40,232);wait_volume(0)
    touch(440,232);wait_volume(100)
    observed=[]
    for x,y,expected in [(240,232,50),(340,232,75),(470,100,100),(10,75,0),(159,75,30)]:
        post('/api/touch',{'x':x,'y':y,'down':True});wait_volume(expected)
        observed.append(volume());assert frames()==frozen
    post('/api/touch',{'x':159,'y':75,'down':False});time.sleep(.7);wait_volume(30)
    shot=out/(args.prefix+'-menu.png')
    subprocess.run([sys.executable,ROOT/'vendor/h1-sdk/scripts/capture_emulator_frame.py',shot],check=True)
    tap(41);touch(100,80);time.sleep(2);assert frames()>frozen+4 and volume()==30
    touch(100,100);touch(100,212);time.sleep(2);assert volume()==original
    tap(39);time.sleep(6);assert volume()==30
    touch(100,100);touch(330,212)
    # Restoring volume precedes the profile log/FAT commit. Keep the guest
    # running after Exit so stopping QEMU cannot interrupt that final write.
    time.sleep(10);assert volume()==original
    stopped=post('/api/stop',{})
    assert not stopped['running'] and stopped['returncode']==0 and stopped['last_error'] is None
    report={'ok':True,'date':args.date,'environment':'Full H1 V1.41 firmware QEMU',
            'physical_hardware_tested':False,
            'bda_sha256':hashlib.sha256(args.bda.read_bytes()).hexdigest(),
            'kernel_sha256':hashlib.sha256(Path(status['kernel']).read_bytes()).hexdigest(),
            'qemu_sha256':hashlib.sha256(Path(status['qemu']).read_bytes()).hexdigest(),
            'menu_screenshot_sha256':hashlib.sha256(shot.read_bytes()).hexdigest(),
            'held_drag_values':observed,'saved_and_reopened_volume':30,
            'original_system_volume_restored':original,
            'status':{k:stopped[k] for k in ('running','returncode','last_error')}}
    (out/(args.prefix+'-native.json')).write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
