"""Check v0.9 loading frames and actual H1 AIC recordings against v0.8."""
import hashlib
import json
from pathlib import Path
import re
import struct
import wave
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
WORK=ROOT/'build/h1-emulator-test'
OUT=WORK/'evidence'

def audio(tag,name):
    with wave.open(str(OUT/(tag+'-'+name+'.wav')),'rb') as f:
        assert (f.getframerate(),f.getnchannels(),f.getsampwidth())==(32000,2,2)
        count=f.getnframes();pcm=struct.unpack('<%dh'%(count*2),f.readframes(count))[::2]
    assert count>32000*18 and min(pcm)<-1000 and max(pcm)>1000
    first=next(i for i,x in enumerate(pcm) if x)
    last=count-1-next(i for i,x in enumerate(reversed(pcm)) if x)
    run=longest=gaps=0
    for value in pcm[first:last+1]:
        if value==0:run+=1;longest=max(longest,run)
        else:
            if run>=320:gaps+=1
            run=0
    return {'seconds':count/32000,'nonzero_fraction':sum(x!=0 for x in pcm)/count,
            'longest_internal_silence_ms':longest/32,'internal_gaps_at_least_10ms':gaps,
            'min':min(pcm),'max':max(pcm)}

def run(tag,version):
    path=OUT/(tag+'-run.log');raw=path.read_bytes();log=raw.decode('gbk')
    assert 'APP_BEGIN version='+version in log and 'APP_END result=0' in log
    counts=re.findall(r'AUDIO_CLOSE_BEGIN batches=(\d+) submitted=(\d+) nonzero=(\d+) dropped=(\d+) failures=(\d+) underruns=(\d+)',log)
    stops=re.findall(r'STOP video=(\d+) errors=(\d+)',log)
    assert len(counts)==len(stops)==2
    assert log.count('JIT_STATE enabled=1')==log.count('JIT_FREE_END')==2
    assert log.count('AUDIO_OPEN_END ready=1')==log.count('AUDIO_CLOSE_END descriptors=1')==2
    results={}
    for name,values,stop in zip(('tone','emerald'),counts,stops):
        assert values[3:5]==('0','0') and stop[1]=='0' and int(stop[0])>100
        results[name]={'video_frames':int(stop[0]),'underruns':int(values[5]),
                       'submitted':int(values[1]),'audio':audio(tag,name)}
    results['log_bytes']=len(raw)
    if version=='0.9':
        assert log.count('AUDIO_OPEN_BEGIN source=32768 output=32000')==2
        assert 'FRAME_BEGIN' not in log and 'ROM_SEEK_BEGIN' not in log
        ticks=[int(x) for x in re.findall(r'LOADING_DONE ticks=(\d+)',log)]
        assert len(ticks)==2 and all(x>0 for x in ticks)
        results['loading_seconds_80hz']=[x/80 for x in ticks]
    return results

def main():
    sha=hashlib.sha256((ROOT/'build/v09-release/H1GBA.bda').read_bytes()).hexdigest()
    assert sha=='4fefd619182ce02507e558e51c94a4dc1d27482e1fa513518d5e2211b523335e'
    baseline_sha=hashlib.sha256((ROOT/'build/v08-release/H1GBA.bda').read_bytes()).hexdigest()
    assert baseline_sha=='ce81e84707432ae270e9230d770ff7769086a261169f7c22d6ab7f77da131c46'
    baseline=run('v09-baseline','0.8');current=run('v09-final','0.9')
    image=Image.open(WORK/'v09-final-tone-loading.png').convert('RGB')
    assert image.size==(480,272)
    teal=sum(image.getpixel((x,135))==(0,180,160) for x in range(50,430))
    assert 0<teal<380,teal
    assert current['tone']['underruns']<baseline['tone']['underruns']
    assert current['tone']['audio']['internal_gaps_at_least_10ms']<baseline['tone']['audio']['internal_gaps_at_least_10ms']
    assert current['tone']['video_frames']>baseline['tone']['video_frames']
    report={'ok':True,'kind':'Complete H1 V1.41 firmware and actual AIC PCM',
            'build_sha256':sha,'baseline_sha256':baseline_sha,'baseline':baseline,'current':current,
            'loading_frame':'v09-final-tone-loading.png','hardware_tested':False,
            'limits':'Short single runs on the same QEMU host; not a 9588 benchmark. Emerald intro silence is natural. Baseline Emerald had existing save slots, v0.9 used new slots.'}
    (OUT/'v09-native-verification.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
