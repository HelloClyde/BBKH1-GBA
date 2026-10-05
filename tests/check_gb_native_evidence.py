"""Check archived v0.7 binary, complete H1 firmware lifecycle, saves and PCM."""
from pathlib import Path
import hashlib
import json
import re
import struct
import wave
import zlib
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
WORK=ROOT/'build/h1-emulator-test'
OUT=WORK/'evidence'

def audio(name):
    with wave.open(str(OUT/('v07-'+name+'.wav')),'rb') as f:
        assert (f.getframerate(),f.getnchannels(),f.getsampwidth())==(32000,2,2)
        count=f.getnframes();samples=struct.unpack('<%dh'%(count*2),f.readframes(count))[::2]
    assert count>=32000*11 and max(samples)-min(samples)>2000
    # GB square-wave DAC output has DC offset; require actual AC variation.
    transitions=sum(a!=b for a,b in zip(samples,samples[1:]))
    fraction=sum(x!=0 for x in samples)/count
    assert transitions>10000 and fraction>.3
    return {'seconds':count/32000,'min':min(samples),'max':max(samples),'nonzero_fraction':fraction,'transitions':transitions}

def save(name,slots):
    valid=[]
    for index in slots:
        data=(OUT/('v07-'+name+'.s'+str(index))).read_bytes()
        magic,version,identity,generation,size,crc,header=struct.unpack_from('<7I',data)
        assert magic==0x31534748 and version==1 and len(data)==size+28
        assert zlib.crc32(data[28:])==crc and zlib.crc32(data[:24])==header
        valid.append((generation,identity,data[28:]))
    generation,identity,data=max(valid)
    if name.endswith(('.gb','.gbc')):
        assert data[:4]==bytes.fromhex('5a11ef42') and data[5]==0xc0
    else: assert data[0]==0x5a
    return generation,identity,data

def main():
    sha=hashlib.sha256((ROOT/'build/v07-release/H1GBA.bda').read_bytes()).hexdigest()
    assert json.loads((OUT/'gb-native-verification.json').read_text())['build_sha256']==sha
    assert json.loads((ROOT/'build/v07-release/H1GBA.build.json').read_text())['sha256']==sha
    log=(OUT/'v07-native-run.log').read_bytes().decode('gbk')
    assert 'APP_BEGIN version=0.7' in log and 'APP_END result=0' in log
    assert log.count('GB_LOAD mode=GB ')==log.count('GB_LOAD mode=GBC ')==2
    assert log.count('CORE_SELECTED name=GBA')==log.count('JIT_STATE enabled=1')==log.count('JIT_FREE_END')==1
    assert log.count('AUDIO_OPEN_END ready=1')==log.count('AUDIO_CLOSE_END descriptors=1')==log.count('GUI_CONTEXT_CLOSE_END')==5
    assert log.count('SAVE_LOAD_END status=1')==2 and 'GB_CORE_ERROR' not in log and 'AUDIO_STALL' not in log
    stops=re.findall(r'STOP video=(\d+) errors=(\d+)',log)
    assert len(stops)==5 and all(int(n)>=10 and e=='0' for n,e in stops),stops
    closes=re.findall(r'AUDIO_CLOSE_BEGIN batches=(\d+) submitted=(\d+) nonzero=(\d+) dropped=(\d+) failures=(\d+) underruns=(\d+)',log)
    assert len(closes)==5 and all(r[3:5]==('0','0') for r in closes)
    records=json.loads((OUT/'v07-native-interaction.json').read_text())
    assert [r['name'] for r in records]==['gb','gbc','gb-restore','gbc-restore','gba']
    for record in records[:2]:
        assert bytes.fromhex(record['A_ram'])[1]==0xa5 and bytes.fromhex(record['right_ram'])[2]&1==0
        assert bytes.fromhex(record['released_ram'])[1:3]==bytes.fromhex('11ef')
    assert [r['cpu_double_speed'] for r in records[:4]]==[0,1,0,1]
    gbgen,gbid,gb=save('GBTEST.gb',[0,1]);cgbgen,cgbid,cgb=save('GBCTEST.gbc',[0,1]);save('AUDIO.gba',[0])
    assert gbid!=cgbid and len(gb)==8192 and len(cgb)==8224 and cgb[8192:8196]==b'RTC1'
    for name in ['gb','gbc']:
        pixels=Image.open(WORK/('v07-'+name+'.png')).convert('RGB')
        colors=set(pixels.getdata());assert len(colors)==5 and pixels.getpixel((0,0))==(0,0,0)
        assert pixels.getpixel((89,50))!=(0,0,0) and pixels.getpixel((391,50))==(0,0,0)
        if name=='gbc':assert {(248,0,0),(0,252,0),(0,0,248)}<=colors
    report={'ok':True,'kind':'Complete H1 V1.41 firmware, QEMU bbkh1','build_sha256':sha,
            'native_picker_formats':['gba','gb','gbc'],'video_frames':[int(n) for n,_ in stops],
            'native_keys':['A','right','release'],'gbc_CPU_double_speed':True,'cross_core_switch':True,
            'save_restore_CRC':True,'save_generations':{'GB':gbgen,'GBC':cgbgen},'different_cartridge_identities':True,
            'audio':{n:audio(n) for n in ['gb','gbc','gba']},
            'audio_runs':[dict(zip(('batches','submitted','nonzero','dropped','failures','underruns'),map(int,r))) for r in closes],
            'exit_desktop_checked':True,'hardware_tested':False,'commercial_GB_GBC_games_tested':False}
    (OUT/'gb-native-verification.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
