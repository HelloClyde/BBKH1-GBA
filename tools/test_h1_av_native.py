"""Compare native H1 loading and actual AIC audio from an open ROM picker."""
import argparse
import json
import subprocess
import sys
import time
from test_h1_gb_native import ROOT, WORK, OUT, get, post, key, tap

def capture(name):
    subprocess.run([sys.executable,ROOT/'vendor/h1-sdk/scripts/capture_emulator_frame.py',WORK/(name+'.png')],check=True)
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag',required=True)
    args=parser.parse_args();results=[]
    for name,row in [('tone',0),('emerald',2)]:
        print(args.tag,name,flush=True)
        for _ in range(row):tap(27)
        recorder=subprocess.Popen([sys.executable,ROOT/'tools/capture_h1_audio.py',OUT/(args.tag+'-'+name+'.wav'),'--seconds','26'])
        begin=time.monotonic();initial=get('/api/status');key(39);time.sleep(.5);key(39,False)
        # Early captures make the loading UI reviewable without slowing every frame.
        time.sleep(.5);capture(args.tag+'-'+name+'-loading')
        first_audio=None
        deadline=begin+30
        while time.monotonic()<deadline:
            status=get('/api/status')
            if first_audio is None and status['audio'].get('frames',0)>initial['audio'].get('frames',0):first_audio=time.monotonic()-begin
            if time.monotonic()-begin>=27:break
            time.sleep(.5)
        recorder.wait(timeout=10);capture(args.tag+'-'+name)
        results.append({'name':name,'first_AIC_seconds':first_audio,'duration_seconds':time.monotonic()-begin,'status':status})
        tap(36);time.sleep(7)
    tap(24);time.sleep(10);capture(args.tag+'-exit');post('/api/stop',{})
    (OUT/(args.tag+'-interaction.json')).write_text(json.dumps(results,indent=2)+'\n')
    subprocess.run([sys.executable,ROOT/'tools/read_h1_test_file.py','--output',OUT/(args.tag+'-run.log')],check=True)
    print('Native AV capture complete',flush=True)
if __name__=='__main__':main()
