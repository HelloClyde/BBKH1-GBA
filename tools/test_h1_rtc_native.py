"""Test user-provided Emerald (GBA row 2) from an already-open H1 ROM picker.

Uses only the private test NAND. Never changes the original dump or ROM.
RTC slots and logs are extracted after QEMU stops.
"""
import json
import re
import subprocess
import sys
import time
from test_h1_gb_native import ROOT, WORK, OUT, get, post, key, tap, memory

def capture(name):
    subprocess.run([sys.executable,ROOT/'vendor/h1-sdk/scripts/capture_emulator_frame.py',
        WORK/('v08-'+name+'.png')],check=True)
def main():
    text=(ROOT/'build/release/H1GBA.map').read_text()
    status_address=int(re.search(r'(0x[0-9a-f]+)\s+rtc_status\b',text)[1],16)
    live={}
    for session in range(2):
        print('Native RTC session',session+1,flush=True)
        tap(27);tap(27);tap(39);time.sleep(25)
        if session==0:
            live['H1_RTC']=memory(0xb0003000,2)
            live['rtc_status']=memory(status_address,1)
        capture('emerald-title-'+str(session+1))
        for step in range(2):
            key(25);time.sleep(2);key(25,False);time.sleep(8)
            capture('emerald-start-%d-%d'%(session+1,step+1))
        if session==1:
            capture('menu-check')
            live['H1_RTC_after']=memory(0xb0003000,2)
            live['status']=get('/api/status')
        tap(36);time.sleep(5)
        capture('rtc-picker-'+str(session+1))
        if session==0:time.sleep(5)
    tap(24);time.sleep(12);capture('exit');post('/api/stop',{})
    (OUT/'v08-rtc-live.json').write_text(json.dumps(live,indent=2)+'\n')
    subprocess.run([sys.executable,ROOT/'tools/read_h1_test_file.py',
        '--output',OUT/'v08-native-run.log'],check=True)
    for slot in (0,1):
        subprocess.run([sys.executable,ROOT/'tools/read_h1_test_file.py',
            '--file','GBA/口袋妖怪 - 绿宝石.gba.rtc.s'+str(slot),
            '--output',OUT/('v08-emerald.rtc.s'+str(slot))],check=True)
    print('Native RTC capture complete; visually check menu-check.png then run checker',flush=True)
if __name__=='__main__':main()
