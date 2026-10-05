"""Check archived v0.8 build against real H1 firmware clock/save evidence."""
import hashlib
import json
from pathlib import Path
import re
import struct
import zlib

ROOT=Path(__file__).resolve().parents[1]
WORK=ROOT/'build/h1-emulator-test'
OUT=WORK/'evidence'
def main():
    sha=hashlib.sha256((ROOT/'build/v08-release/H1GBA.bda').read_bytes()).hexdigest()
    assert sha=='ce81e84707432ae270e9230d770ff7769086a261169f7c22d6ab7f77da131c46'
    log=(OUT/'v08-native-run.log').read_bytes().decode('gbk')
    assert 'APP_BEGIN version=0.8' in log and 'APP_END result=0' in log
    assert log.count('RTC_BEGIN source=H1')==2
    assert 'RTC_SAVE_LOAD status=0 bytes=32' in log and 'RTC_SAVE_LOAD status=1 bytes=32' in log
    restored=re.findall(r'RTC_RESTORE seconds=(\d+) offline=(\d+) status=40',log)
    assert len(restored)==1 and int(restored[0][1])>0
    assert log.count('JIT_STATE enabled=1')==log.count('JIT_FREE_END')==2
    assert log.count('AUDIO_OPEN_END ready=1')==log.count('AUDIO_CLOSE_END descriptors=1')==2
    stops=re.findall(r'STOP video=(\d+) errors=(\d+)',log)
    assert len(stops)==2 and all(int(n)>100 and e=='0' for n,e in stops)
    assert 'SAVE restore failed' not in log and 'RTC state cannot' not in log
    states=[]
    for slot in (0,1):
        data=(OUT/('v08-emerald.rtc.s'+str(slot))).read_bytes()
        header=struct.unpack('<7I',data[:28]);state=struct.unpack('<8I',data[28:])
        assert len(data)==60 and header[0]==0x31534748 and header[1]==1 and header[4]==32
        assert header[5]==zlib.crc32(data[28:]) and header[6]==zlib.crc32(data[:24])
        assert state[:2]==(0x31435452,1) and state[4]==0x40
        states.append({'generation':header[3],'clock':state[2],'host':state[3]})
    live=json.loads((OUT/'v08-rtc-live.json').read_text())
    assert live['H1_RTC'][0]&1 and live['H1_RTC_after'][1]>live['H1_RTC'][1]
    assert live['rtc_status']==[64]
    for name in ['v08-menu-check.png','v08-exit.png']:assert (WORK/name).is_file()
    report={'ok':True,'build_sha256':sha,'kind':'Complete H1 V1.41 firmware, QEMU bbkh1',
        'rom':'user-owned Emerald, Chinese filename','video_frames':[int(n) for n,_ in stops],
        'H1_hardware_clock':True,'RTC_restore_offline_seconds':int(restored[0][1]),'RTC_slots':states,
        'menu_screenshot':'v08-menu-check.png','battery_warning_absent_visually_verified':True,
        'exit_result':0,'hardware_tested':False}
    (OUT/'rtc-native-verification.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
