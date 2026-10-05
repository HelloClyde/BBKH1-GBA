"""Compare actual BDA scaler instructions and pixels on identical input frames.

Unicorn instruction counts are CPU-work evidence, not H1 bus time or FPS.
No firmware, disk image, physical device or user ROM is accessed.
"""
import argparse, hashlib, json, re, struct
from pathlib import Path
from unicorn import UC_HOOK_BLOCK
from unicorn.mips_const import *
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tests'))
from mips_smoke import Machine, ROOT

def source(width, height, pattern):
    values=[]; state=123456789
    for y in range(height):
        for x in range(width + 4):
            state=(1664525*state+1013904223)&0xffffffff
            values.append(0xa55a if x>=width else
                          0x07e0 if pattern=='flat' else
                          (y*4057)&65535 if pattern=='stripes' else
                          ((x*977+y*4057)&65535 if width//3<x<width*2//3 and height//3<y<height*2//3 else 31) if pattern=='sprite' else
                          (0xffff if (x+y)&1 else 0) if pattern=='checker' else
                          (x*977+y*4057)&65535 if pattern=='color' else state>>16)
    return struct.pack('<'+'H'*len(values),*values)

def run(bda, map_path, width, height, pattern, mode=3):
    m=Machine(bda,path=None)
    entry=int(re.search(r'(0x[0-9a-f]+)\s+scale_frame_rgb32\s*$',map_path.read_text(),re.M)[1],16)
    src,dst,sp=0x81000000,0x81100000,0x83aff000
    m.write(src,source(width,height,pattern))
    m.write(dst,bytes(480*272*4))
    def invoke(clear):
        m.finished=False
        for reg,value in [(UC_MIPS_REG_A0,dst),(UC_MIPS_REG_A1,src),
                          (UC_MIPS_REG_A2,(width+4)*2),(UC_MIPS_REG_A3,mode),
                          (UC_MIPS_REG_SP,sp),(UC_MIPS_REG_RA,0x80001ff0)]:
            m.uc.reg_write(reg,value)
        m.write(sp+16,struct.pack('<3I',width,height,clear))
        m.uc.emu_start(entry,0,count=20000000)
        assert m.finished,'Scaler did not return'
    stats={'instructions':0,'multiply':0,'mxu_vector_mul_mac':0,'loads':0,'stores':0,'branches':0}
    cache={}
    def block(uc,addr,size,data):
        if addr==0x80001ff0:return
        key=(addr,size)
        if key not in cache:
            words=struct.unpack('<'+'I'*(size//4),m.read(addr,size))
            cache[key]={
                'instructions':len(words),
                'multiply':sum((v>>26==28 and v&63==2) or (v>>26==0 and v&63 in (24,25)) for v in words),
                'mxu_vector_mul_mac':sum(v>>26==28 and v&63 in (0x38,0x3a) for v in words),
                'loads':sum(v>>26 in (32,33,34,35,36,37,38) or (v>>26==28 and v&63==0x10) for v in words),
                'stores':sum(v>>26 in (40,41,42,43,46) or (v>>26==28 and v&63==0x11) for v in words),
                'branches':sum(v>>26 in (1,2,3,4,5,6,7) or (v>>26==0 and v&63 in (8,9)) for v in words)}
        for name,value in cache[key].items():stats[name]+=value
    hook=m.uc.hook_add(UC_HOOK_BLOCK,block)
    invoke(1) # Exclude LUT/coordinate initialization and border clearing.
    for name in stats:stats[name]=0
    invoke(0);m.uc.hook_del(hook)
    assert stats['instructions']>100000,stats
    return stats,m.read(dst,480*272*4)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--baseline',type=Path,required=True)
    p.add_argument('--baseline-map',type=Path,required=True)
    p.add_argument('--candidate',type=Path,required=True)
    p.add_argument('--candidate-map',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args(); cases=[]
    for width,height in [(240,160),(160,144)]:
        for pattern in ['flat','checker','color','random','stripes','sprite']:
            old,pixels=run(a.baseline,a.baseline_map,width,height,pattern)
            new,result=run(a.candidate,a.candidate_map,width,height,pattern)
            assert result==pixels,f'Pixel change: {width}x{height} {pattern}'
            case={'size':[width,height],'pattern':pattern,'baseline':old,'candidate':new,
                  'instruction_reduction_percent':100*(old['instructions']-new['instructions'])/old['instructions'],
                  'pixel_sha256':hashlib.sha256(result).hexdigest(),'identical_pixels':True}
            cases.append(case);print(json.dumps(case),flush=True)
    for mode in (0,1,2):
        for width,height in [(240,160),(160,144)]:
            old,pixels=run(a.baseline,a.baseline_map,width,height,'random',mode)
            new,result=run(a.candidate,a.candidate_map,width,height,'random',mode)
            assert pixels==result,'Existing display mode changed'
    report={'environment':'Unicorn MIPS32; independent MXU1 lane model for new BDA; instruction counts, no bus timing',
            'baseline_sha256':hashlib.sha256(a.baseline.read_bytes()).hexdigest(),
            'candidate_sha256':hashlib.sha256(a.candidate.read_bytes()).hexdigest(),
            'cases':cases,'existing_modes_identical':True}
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')

if __name__=='__main__':main()
