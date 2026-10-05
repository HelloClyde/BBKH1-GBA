"""Measure real H1 firmware Continue latency using the AUDIO.gba framebuffer.

Start with the ROM picker open on row 0. Only the private test NAND is used.
Framebuffer detection works with historical packages without ELF symbols.
"""
import argparse,json,re,subprocess,sys,time,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'vendor/h1-sdk/scripts'))
from capture_emulator_frame import convert_frame,encode_png
from test_h1_gb_native import get,post,tap,memory,URL

def frame():
    with urllib.request.urlopen(URL+'/api/debug/frame',timeout=10) as response:
        return convert_frame(response.read())
def is_game(data):
    w,h,p=data;assert (w,h)==(480,272)
    r,g,b=p[(120*w+100)*4:(120*w+100)*4+3]
    return r>240 and g<20 and b<20
def wait_display(game,timeout=8):
    start=time.monotonic()
    while time.monotonic()-start<timeout:
        data=frame()
        if is_game(data)==game:return time.monotonic()-start,data
        time.sleep(.02)
    raise AssertionError('Timed out waiting for '+('game' if game else 'pause menu'))
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--label',required=True)
    p.add_argument('--map',type=Path);p.add_argument('--cycles',type=int,default=3)
    p.add_argument('--capture-audio',action='store_true')
    p.add_argument('--already-paused',action='store_true',help='Resume a failed measurement left at the menu')
    a=p.parse_args();out=ROOT/'build/h1-emulator-test/evidence';out.mkdir(exist_ok=True)
    counter=None
    if a.map:
        counter=int(re.search(r'\.bss.total_frames\s+(0x[0-9a-f]+)',a.map.read_text())[1],16)
        assert 0x83c00000<counter<0x83ff0000
    if not a.already_paused:
        tap(39);wait_display(True,12);time.sleep(10)
    rows=[]
    for cycle in range(a.cycles):
        if cycle or not a.already_paused: tap(31)
        _,data=wait_display(False,12)
        time.sleep(.5);paused=get('/api/status')['audio']['frames'];time.sleep(.4)
        dma_stopped=get('/api/status')['audio']['frames']==paused
        # Reused open device can keep AIC DMA running, but must output silence.
        if not dma_stopped:
            silent=out/(a.label+'-paused-%d.wav'%cycle)
            subprocess.run([sys.executable,ROOT/'tools/capture_h1_audio.py',silent,'--seconds','2'],check=True)
            assert json.loads(silent.with_suffix('.json').read_text())['nonzero_samples']==0,'Game audio continues in menu'
        if counter:
            frozen=memory(counter,1)[0];time.sleep(.2)
            assert memory(counter,1)[0]==frozen,'Core runs while paused'
        (out/(a.label+'-pause.png')).write_bytes(encode_png(*data))
        post('/api/touch',{'x':115,'y':80,'down':True});time.sleep(.25)
        start=time.monotonic();post('/api/touch',{'x':115,'y':80,'down':False})
        _,data=wait_display(True,8);latency=time.monotonic()-start
        (out/(a.label+'-resumed.png')).write_bytes(encode_png(*data))
        time.sleep(.5)
        first=memory(counter,1)[0] if counter else None
        sample_start=time.monotonic()
        if a.capture_audio and cycle==0:
            subprocess.run([sys.executable,ROOT/'tools/capture_h1_audio.py',out/(a.label+'-resumed.wav'),'--seconds','8'],check=True)
        else: time.sleep(8)
        last=memory(counter,1)[0] if counter else None
        duration=time.monotonic()-sample_start
        if counter: assert last>first,'Invalid frame counter or stalled core'
        rows.append({'cycle':cycle+1,'resume_display_latency_s':round(latency,4),
            'frames':last-first if counter else None,'interval_s':round(duration,4),
            'logic_fps':round((last-first)/duration,3) if counter else None,'paused_audio_silent':True,'paused_dma_stopped':dma_stopped})
        print(rows[-1],flush=True)
    tap(24);time.sleep(4);status=post('/api/stop',{})
    assert not status['running'] and status['returncode']==0 and not status['last_error']
    report={'label':a.label,'bda_sha256':json.loads((ROOT/'build/h1-emulator-test/image-build.json').read_text(encoding='utf-8'))['bda_sha256'],
        'counter':hex(counter) if counter else None,'cycles':rows,'status':status,
        'note':'QEMU full H1 V1.41; latency includes HTTP/frame capture. Not physical H1 speed.'}
    (out/(a.label+'-resume.json')).write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
