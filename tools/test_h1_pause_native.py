"""Functional touch-menu test in complete V1.41 firmware, starting in tone's mapping page.
Never writes guest RAM or the original H1 dump. Test inputs use emulator APIs;
readback of native CPU state verifies actual core restore before resuming.
"""
import hashlib,json,re,subprocess,sys,time
from pathlib import Path
from test_h1_gb_native import ROOT,WORK,OUT,get,post,tap,key,memory,wait_ram

def sym(name):
    return int(re.search(r'(0x[0-9a-f]+)\s+'+name+r'\s*$',(ROOT/'build/release/H1GBA.map').read_text(),re.M)[1],16)
def local(name):
    return int(re.search(r'\.bss\.'+name+r'\s+(0x[0-9a-f]+)',(ROOT/'build/release/H1GBA.map').read_text())[1],16)
def touch(x,y):
    post('/api/touch',{'x':x,'y':y,'down':True});time.sleep(.25)
    post('/api/touch',{'x':x,'y':y,'down':False});time.sleep(.6)
def shot(name):
    subprocess.run([sys.executable,ROOT/'vendor/h1-sdk/scripts/capture_emulator_frame.py',WORK/('v10-'+name+'.png')],check=True)
def record(name,seconds=5):
    subprocess.run([sys.executable,ROOT/'tools/capture_h1_audio.py',OUT/('v10-'+name+'.wav'),'--seconds',str(seconds)],check=True)
    return json.loads((OUT/('v10-'+name+'.json')).read_text())
def quiet(name):
    # The firmware closes AIC while paused/muted, so no WAV packets exist.
    before=get('/api/status')['audio'];time.sleep(5);after=get('/api/status')['audio']
    assert before['sequence']==after['sequence'] and before['frames']==after['frames'],(name,before,after)
    data={'no_new_audio_packets':True,'before':before,'after':after}
    (OUT/('v10-'+name+'.json')).write_text(json.dumps(data,indent=2)+'\n')
    return data
def checkpoint(report):
    (OUT/'v10-native-interaction.json').write_text(json.dumps(report,indent=2)+'\n')
def paused(name):
    before=memory(local('total_frames'),1);time.sleep(2);after=memory(local('total_frames'),1)
    assert before==after,(name,before,after)
    return before[0]
def main():
    OUT.mkdir(exist_ok=True)
    report={'bda_sha256':hashlib.sha256((ROOT/'dist/H1GBA.bda').read_bytes()).hexdigest(),'runs':[]}
    # Mapping page was opened by touch during the initial coordinate probe.
    touch(100,132);tap(1);shot('mapping-q-native');touch(320,240)
    touch(100,175);touch(120,72);touch(120,112);touch(120,112);shot('display-native');tap(41)
    for kind,row in [('tone',None),('gb',3),('gbc',4),('emerald',2)]:
        print('Native test',kind,flush=True)
        if row is not None:
            for _ in range(row):tap(27)
            tap(39);time.sleep(8 if kind!='emerald' else 20)
            touch(100,100)
        result={'kind':kind,'paused_at':paused(kind)}
        cpu=sym('reg' if kind in ('tone','emerald') else 'h1gb_cpu')
        original=memory(cpu,16 if kind in ('tone','emerald') else 14)
        shot(kind+'-pause-native')
        touch(100,130);touch(100,72);time.sleep(3);shot(kind+'-saved-native')
        tap(41);touch(100,80);time.sleep(4)
        if kind in ('gb','gbc'):
            # Separate per-ROM mappings: A starts at Z, then changes to Q.
            key(16);result['default_A_ram']=wait_ram(lambda d:d[1]==0xa5);key(16,False)
            touch(100,100);touch(320,80);touch(100,132);tap(1);touch(320,240);touch(100,80)
            key(1);result['mapped_A_ram']=wait_ram(lambda d:d[1]==0xa5);key(1,False)
            result['released_ram']=wait_ram(lambda d:d[1]==0x11)
        elif kind=='tone':
            key(1);time.sleep(1);shot('tone-remapped-a-native');key(1,False)
        touch(100,100);result['paused_again_at']=paused(kind)
        result['cpu_advanced_before_load']=memory(cpu,len(original))!=original
        touch(320,130);touch(100,72);time.sleep(3)
        restored=memory(cpu,len(original));assert restored==original,(kind,original,restored)
        result['cpu_restored']=True;shot(kind+'-loaded-native')
        tap(41);touch(100,80);time.sleep(3)
        result['frames_after_resume']=memory(local('total_frames'),1)[0]
        assert result['frames_after_resume']>result['paused_again_at']
        if kind=='tone':
            result['audio_resumed']=record('tone-resumed');assert result['audio_resumed']['nonzero_samples']>1000
            touch(100,100);time.sleep(1)
            result['audio_paused']=quiet('tone-paused')
            # Mute, resume and verify silent play; turn it back on before switching.
            touch(320,175);touch(100,80);time.sleep(1)
            result['audio_muted']=quiet('tone-muted')
            touch(100,100);touch(320,175)
        else:touch(100,100)
        report['runs'].append(result);checkpoint(report)
        touch(100,230) if kind!='emerald' else touch(320,230)
        time.sleep(4)
    time.sleep(7);report['stop_status']=post('/api/stop',{});checkpoint(report)
    print('PASS complete firmware touch, CPU restore, audio pause/resume, mapping, ROM switch and exit',flush=True)
if __name__=='__main__':main()
