"""Verify GUI+0x9D8 D+K combinations through three cores in private H1 firmware.
Start at the native ROM picker; all mapping changes use the app's own menu.
"""
import hashlib,json,re,subprocess,sys,time
from pathlib import Path
from test_h1_gb_native import get,post,tap,key,memory,ROOT

def touch(x,y):
    post('/api/touch',{'x':x,'y':y,'down':True});time.sleep(.25)
    post('/api/touch',{'x':x,'y':y,'down':False});time.sleep(.5)

def main():
    text=(ROOT/'build/release/H1GBA.map').read_text()
    def sym(name):return int(re.search(r'(0x[0-9a-f]+)\s+'+name+r'\s*$',text,re.M)[1],16)
    addr=int(re.search(r'\.bss\.input\s+(0x[0-9a-f]+)',text)[1],16)
    io=sym('io_registers');ram=sym('h1gb_ram')
    out=ROOT/'build/h1-emulator-test/evidence';out.mkdir(parents=True,exist_ok=True);results=[]
    def readback(kind):
        mask=memory(addr+100,1)[0]&65535
        if kind=='gba':state={'keyinput':memory(io+0x130,1)[0]&1023}
        else:
            bank=memory(ram+33024,1)[0]
            data=b''.join(w.to_bytes(4,'little') for w in memory(bank,2))
            state={'cartridge_ram':data.hex(),'a':data[1]==0xa5,'right':not bool(data[2]&1)}
        return {'mask':mask,**state}
    def expect(kind,mask):
        deadline=time.monotonic()+4
        while time.monotonic()<deadline:
            data=readback(kind)
            if data['mask']==mask:
                if kind=='gba':
                    gba_mask=(1 if mask&256 else 0)|(16 if mask&128 else 0)
                    if data['keyinput']==(1023^gba_mask):return data
                elif data['a']==bool(mask&256) and data['right']==bool(mask&128):return data
            time.sleep(.08)
        raise AssertionError((kind,mask,data))
    for kind,row in [('gba',0),('gb',3),('gbc',4)]:
        for _ in range(row):tap(27)
        tap(39);time.sleep(5)
        # Pause and map A=K, Right=D using actual touch/keyboard UI.
        touch(30,30);touch(330,80);touch(70,132);tap(32)
        touch(330,100);tap(10);tap(41);tap(39);time.sleep(2)
        steps=[{'step':'released','state':expect(kind,0)}]
        for label,code,down,want in [('D down',10,True,128),('K while D',32,True,384),
            ('release K keep D',32,False,128),('K while D again',32,True,384),
            ('release D keep K',10,False,256),('release K',32,False,0),
            ('K first',32,True,256),('D while K',10,True,384),
            ('release K keep D reversed',32,False,128),('release D',10,False,0)]:
            key(code,down);steps.append({'step':label,'state':expect(kind,want)})
        result={'core':kind,'steps':steps};results.append(result)
        print('PASS native',kind,'D+K, both press orders and independent releases',flush=True)
        touch(30,30);time.sleep(.4)
        paused=int(re.search(r'\.bss\.total_frames\s+(0x[0-9a-f]+)',text)[1],16)
        frames=memory(paused,1)[0];time.sleep(1);assert memory(paused,1)[0]==frames
        tap(39);time.sleep(.6);assert memory(paused,1)[0]>frames
        tap(36 if kind!='gbc' else 24);time.sleep(3)
    status=post('/api/stop',{});assert not status['running'] and status['returncode']==0
    report={'ok':True,'environment':'qemu','bda_sha256':hashlib.sha256((ROOT/'dist/H1GBA.bda').read_bytes()).hexdigest(),
            'gui_api':'0x9D8','mapping_ui':True,'cores':results,'status':status}
    (out/'v121-combo-native.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print('PASS native GUI query and three-core combination delivery',flush=True)
if __name__=='__main__':main()
