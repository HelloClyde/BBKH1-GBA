"""Test TCU profiling, wrap, long menu pause, resume and release in private H1 QEMU.
Start at the native ROM picker. Never accesses a physical device or user dump.
"""
import argparse,hashlib,json,os,re,sys,time
import subprocess
from pathlib import Path
from test_h1_gb_native import get,post,tap,memory,WORK
ROOT=Path(__file__).resolve().parents[1]
def tcu():
    return {'enabled':memory(0x10002010,1)[0]&32,
            'stopped':memory(0x1000201c,1)[0]&32,
            'mask':memory(0x10002030,1)[0]&0x200020,
            'registers':memory(0x10002090,4)}
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--row',type=int,default=2)
    p.add_argument('--steady-seconds',type=float,default=8)
    p.add_argument('--expect-heartbeat',action='store_true')
    p.add_argument('--linear',action='store_true')
    p.add_argument('--audio',type=Path,help='Capture 8 seconds of actual AIC PCM after stable resume')
    p.add_argument('--map',type=Path,default=ROOT/'build/release-profile/H1GBA.map')
    p.add_argument('--output',type=Path,default=ROOT/'build/h1-emulator-test/evidence/v111-tcu-native.json')
    a=p.parse_args()
    a.output.parent.mkdir(parents=True,exist_ok=True)
    emulator_root=Path(os.environ.get('H1_EMULATOR_ROOT',str(ROOT/'.tools/h1-emulator')))
    assert a.steady_seconds>0
    text=a.map.read_text()
    match=re.search(r'(0x[0-9a-f]+)\s+total_frames\b',text)
    if not match: match=re.search(r'\.bss\.total_frames\s+(0x[0-9a-f]+)',text)
    addr=int(match[1],16)
    counter_fault=re.search(r'\.bss\.pc_fault\s+(0x[0-9a-f]+)',text)
    assert counter_fault,'Missing pc_fault symbol in profile build'
    fault_addr=int(counter_fault[1],16)
    profile_fault=re.search(r'\.bss\.fault\s+(0x[0-9a-f]+)\s+0x4\s+[^\n]*profile[^\n]*',text)
    assert profile_fault,'Missing profiler fault symbol'
    profile_fault_addr=int(profile_fault[1],16)
    before=tcu();assert before['enabled']==0
    for _ in range(a.row):tap(27)
    tap(39);time.sleep(10)
    first=memory(addr,1)[0];running=tcu();assert running['enabled']==32
    remaining=a.steady_seconds
    while remaining>0:
        interval=min(30,remaining);time.sleep(interval);remaining-=interval
    second=memory(addr,1)[0];assert second>first+100
    heartbeat_count=None
    if a.expect_heartbeat:
        symbol=re.search(r'\.bss\.heartbeat_count\s+(0x[0-9a-f]+)',text)
        assert symbol,'Missing heartbeat RAM counter'
        heartbeat_count=memory(int(symbol[1],16),1)[0]
        assert heartbeat_count>0,'Expected a heartbeat retained in RAM after long run'
    assert memory(fault_addr,1)[0]==0,'TCU read fault while running across wraps'
    assert memory(profile_fault_addr,1)[0]==0,'Profiler invalidated while running'
    tap(31);time.sleep(3)
    subprocess.run([sys.executable,ROOT/'vendor/h1-sdk/scripts/capture_emulator_frame.py',a.output.with_name(a.output.stem+'-pause.png')],check=True)
    paused=memory(addr,1)[0];paused_tcu=tcu()
    assert paused_tcu==before,(paused_tcu,before)
    time.sleep(6);assert memory(addr,1)[0]==paused
    if a.linear:
        tap(27);tap(27);tap(39) # Display settings, starting at root Continue.
        tap(39);tap(39) # Aspect nearest -> stretch -> aspect linear.
        input_symbol=re.search(r'\.bss\.input\s+(0x[0-9a-f]+)\s+0x80\s+[^\n]*-app[^\n]*',text)
        assert input_symbol,'Missing frontend input state'
        assert memory(int(input_symbol[1],16)+112,1)[0]==3,'Linear aspect was not selected'
        subprocess.run([sys.executable,ROOT/'vendor/h1-sdk/scripts/capture_emulator_frame.py',a.output.with_name(a.output.stem+'-linear-settings.png')],check=True)
        tap(41) # Back resets root selection to Continue.
    tap(39);time.sleep(10)
    resumed=memory(addr,1)[0];assert resumed>paused+100
    assert tcu()['enabled']==32
    assert memory(fault_addr,1)[0]==0,'TCU read fault after resume'
    assert memory(profile_fault_addr,1)[0]==0,'Profiler invalidated after resume'
    if a.linear:
        subprocess.run([sys.executable,ROOT/'vendor/h1-sdk/scripts/capture_emulator_frame.py',a.output.with_name(a.output.stem+'-linear-game.png')],check=True)
    if a.audio:
        subprocess.run([sys.executable,ROOT/'tools/capture_h1_audio.py',a.audio,'--seconds','8'],check=True)
    tap(24);time.sleep(4);released=tcu();assert released==before,(released,before)
    status=post('/api/stop',{})
    assert not status['running'] and status['returncode']==0 and not status['last_error']
    report={'environment':'qemu','bda_sha256':json.loads((WORK/'image-build.json').read_text(encoding='utf-8'))['bda_sha256'],
            'qemu_sha256':hashlib.sha256(Path(status['qemu']).read_bytes()).hexdigest(),
            'tcu_source_sha256':hashlib.sha256((emulator_root/'qemu/overlay/hw/timer/jz4740_tcu.c').read_bytes()).hexdigest(),
            'frames_before':first,'frames_after':second,'frames_paused':paused,'frames_resumed':resumed,
            'steady_seconds':a.steady_seconds,'heartbeat_ram_count':heartbeat_count,
            'linear_selected':a.linear,
            'audio_capture':json.loads(a.audio.with_suffix('.json').read_text()) if a.audio else None,
            'before_tcu':before,'running_tcu':running,'paused_tcu':paused_tcu,'released_tcu':released,'status':status}
    a.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print('PASS TCU runs across wraps, releases for long menu pause, reacquires on resume and restores on exit',flush=True)
if __name__=='__main__':main()
