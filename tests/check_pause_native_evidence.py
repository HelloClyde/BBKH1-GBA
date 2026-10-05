"""Check current v0.10 BDA against complete-firmware touch/save/audio evidence.
QEMU must be stopped before reading private NAND. Does not touch source dumps.
"""
import hashlib,json,re,struct,sys,zlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from read_h1_test_file import H1Nand,Fat16
WORK=ROOT/'build/h1-emulator-test';OUT=WORK/'evidence'
def checked_blob(volume,path,dest):
    data=volume.file(path);header=struct.unpack_from('<7I',data)
    assert header[0:2]==(0x31534748,1) and header[4]==len(data)-28
    assert header[5]==zlib.crc32(data[28:]) and header[6]==zlib.crc32(data[:24])
    dest.write_bytes(data)
    return data[28:],header[3]
def main():
    sha=hashlib.sha256((ROOT/'dist/H1GBA.bda').read_bytes()).hexdigest()
    live=json.loads((OUT/'v10-native-interaction.json').read_text())
    assert live['bda_sha256']==sha==json.loads((WORK/'image-build.json').read_text())['bda_sha256']
    assert [r['kind'] for r in live['runs']]==['tone','gb','gbc','emerald']
    assert live['stop_status']['running'] is False and not live['stop_status']['last_error']
    for run in live['runs']:
        assert run['cpu_restored'] and run['paused_again_at']>run['paused_at'] and run['frames_after_resume']>run['paused_again_at']
        # Tone's tiny periodic loop can stop with identical ARM registers at
        # different frame boundaries; require changed CPU state for real-game
        # and SM83 runs, while retaining the observed tone result verbatim.
        if run['kind']!='tone':assert run['cpu_advanced_before_load']
        if run['kind'] in ('gb','gbc'):
            assert run['default_A_ram'].startswith('5aa5') and run['mapped_A_ram'].startswith('5aa5') and run['released_ram'].startswith('5a11')
    tone=live['runs'][0]
    assert tone['audio_resumed']['nonzero_samples']>1000
    assert tone['audio_paused']['no_new_audio_packets'] and tone['audio_muted']['no_new_audio_packets']
    nand=H1Nand(WORK/'h1-system.raw');results=[]
    try:
        assert not nand.torn
        volume=Fat16(nand);raw=volume.file('GBA/h1gba.log');log=raw.decode('gbk')
        assert raw==(OUT/'v10-native-run.log').read_bytes()
        assert 'APP_BEGIN version=0.10' in log and 'APP_END result=0' in log
        assert log.count('STATE_SAVE slot=1 status=1')>=4 and log.count('STATE_LOAD slot=1 status=1')>=4
        assert 'status=-1' not in log and 'status=-2' not in log
        stops=re.findall(r'STOP video=(\d+) errors=(\d+)',log)
        assert len(stops)==4 and all(int(n)>100 and e=='0' for n,e in stops)
        roms=re.findall(r'ROM_PATH length=\d+ path=(.*)',log)
        assert len(roms)==4
        for kind,rom in zip(('tone','gb','gbc','emerald'),roms):
            name=rom.strip().rsplit('\\',1)[1];states=[]
            for slot in (0,1):
                try:payload,generation=checked_blob(volume,'GBA/'+name+'.st1.s'+str(slot),OUT/('v10-'+kind+'.st1.s'+str(slot)))
                except FileNotFoundError:continue
                fields=struct.unpack_from('<6I',payload)
                assert fields[:3]==(0x31545348,1,1 if kind in ('tone','emerald') else 2)
                assert len(payload)==24+sum(fields[3:])
                states.append({'slot':slot,'generation':generation,'core_bytes':fields[3],'ram_bytes':fields[4],'rtc_bytes':fields[5]})
            assert states
            configs=[]
            for slot in (0,1):
                try:cfg,generation=checked_blob(volume,'GBA/'+name+'.cfg.s'+str(slot),OUT/('v10-'+kind+'.cfg.s'+str(slot)))
                except FileNotFoundError:continue
                magic,version,scale,skip,sound=struct.unpack_from('<5I',cfg)
                assert (magic,version)==(0x31474643,1)
                assert cfg[21]==9 and cfg[36]==0 and cfg[59]==0 # Q=A, Z/confirm cleared
                configs.append({'generation':generation,'scale':scale,'skip':skip,'sound':sound})
            if kind!='emerald':assert configs
            results.append({'kind':kind,'states':states,'configs':configs,'video_frames':int(stops[len(results)][0])})
    finally:nand.stream.close()
    for kind in ('tone','gb','gbc','emerald'):
        for stage in ('pause','saved','loaded'):assert (WORK/('v10-'+kind+'-'+stage+'-native.png')).is_file()
    report={'ok':True,'kind':'Complete H1 V1.41 firmware, QEMU bbkh1','sha256':sha,
        'results':results,'torn_records':0,'hardware_tested':False,'core_cpu_restored':True,
        'paused_audio_stopped':True,'muted_audio_stopped':True,'resumed_audio_nonzero':True}
    (OUT/'v10-native-verification.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
