"""Drive an already-open ROM picker in the private H1 firmware test image.

Requires GBTEST.gb, GBCTEST.gbc, AUDIO.gba from the original test generators.
The order follows H1's grouped extension filtering: GBA rows 0..2, GB 3, GBC 4.
"""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
WORK=Path(os.environ.get('H1_TEST_WORK',str(ROOT/'build/h1-emulator-test')))
OUT=WORK/'evidence'
URL='http://127.0.0.1:8793'

def get(path): return json.load(urllib.request.urlopen(URL+path,timeout=10))
def post(path,data):
    return json.load(urllib.request.urlopen(urllib.request.Request(URL+path,json.dumps(data).encode(),{'Content-Type':'application/json'}),timeout=10))
def key(code,down=True): post('/api/key',{'code':code,'down':down})
def tap(code): key(code);time.sleep(.5);key(code,False);time.sleep(.4)
def capture(name): subprocess.run([sys.executable,ROOT/'vendor/h1-sdk/scripts/capture_emulator_frame.py',WORK/('v07-'+name+'.png')],check=True)
def memory(address,count):
    result=get('/api/debug/memory?address=0x%x&count=%d'%(address&0x1fffffff,count))
    words=[]
    for line in result['memory'].splitlines():
        if ':' in line: words.extend(int(x,16) for x in re.findall(r'0x([0-9a-fA-F]{8})',line.split(':',1)[1]))
    return words
def gb_ram():
    text=(ROOT/'build/release/H1GBA.map').read_text()
    addr=int(re.search(r'(0x[0-9a-f]+)\s+h1gb_ram\b',text)[1],16)
    pointer=memory(addr+33024,1)[0]
    assert 0x80000000<=pointer<0x83c00000,hex(pointer)
    data=b''.join(x.to_bytes(4,'little') for x in memory(pointer,2))
    return data
def wait_ram(test):
    deadline=time.monotonic()+8
    while time.monotonic()<deadline:
        data=gb_ram()
        if test(data): return data.hex()
        time.sleep(.3)
    raise AssertionError('Native key did not reach cartridge: '+gb_ram().hex())
def audio(name):
    subprocess.run([sys.executable,ROOT/'tools/capture_h1_audio.py',OUT/('v07-'+name+'.wav'),'--seconds','12'],check=True)

def main():
    OUT.mkdir(exist_ok=True);results=[]
    for name,row in [('gb',3),('gbc',4),('gb-restore',3),('gbc-restore',4),('gba',0)]:
        print('Selecting',name,flush=True)
        for _ in range(row):tap(27)
        tap(39);time.sleep(16);capture(name)
        result={'name':name,'status':get('/api/status')}
        if name!='gba':
            result['initial_ram']=gb_ram().hex()
            assert result['initial_ram'].startswith('5a11ef42'),result
            if name.endswith('restore'): assert gb_ram()[5]==0xc0,result
            address=int(re.search(r'(0x[0-9a-f]+)\s+h1gb_cpu\b',(ROOT/'build/release/H1GBA.map').read_text())[1],16)
            result['cpu_double_speed']=memory(address+32,1)[0]
            assert result['cpu_double_speed']==int(name.startswith('gbc')),result
        if name in ('gb','gbc'):
            audio(name)
            key(16)
            result['A_ram']=wait_ram(lambda d:d[1]==0xa5)
            key(16,False)
            result['A_release_ram']=wait_ram(lambda d:d[1]==0x11)
            key(35)
            result['right_ram']=wait_ram(lambda d:d[2]&1==0)
            key(35,False)
            result['released_ram']=wait_ram(lambda d:d[1]==0x11 and d[2]&1==1)
        if name=='gba':audio(name)
        results.append(result)
        (OUT/'v07-native-interaction.json').write_text(json.dumps(results,indent=2)+'\n',encoding='utf-8')
        tap(24 if name=='gba' else 36);time.sleep(4)
        capture('exit' if name=='gba' else name+'-picker')
    post('/api/stop',{})
    print('PASS native GB/GBC audio, A/right/release, save restore, GBA switch and exit',flush=True)

if __name__=='__main__':main()
