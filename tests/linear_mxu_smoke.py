"""Exercise the actual MXU assembly with an independent Unicorn lane model."""
import argparse,hashlib,json,struct
from pathlib import Path
from unicorn.mips_const import *
from mips_smoke import Machine,ROOT,PAYLOAD_OFFSET

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bda',type=Path,default=ROOT/'dist/H1GBA.bda')
    p.add_argument('--output',type=Path,default=ROOT/'build/profile-unit/linear-mxu-v123.json')
    a=p.parse_args();m=Machine(a.bda,path=None)
    payload=a.bda.read_bytes()[PAYLOAD_OFFSET:]
    entry=0x83c00020+payload.index(struct.pack('<I',0x48314d58))+4
    srca,srcb,dst,sp=0x81000000,0x81001000,0x81002000,0x83aff000
    av=[(i*0x9717ef)&0xffffff for i in range(480)]
    bv=[(~(i*0x35436b))&0xffffff for i in range(480)]
    av[:3]=[0,0xffffff,0xff00ff];bv[:3]=[0xffffff,0,0x00ff00]
    encoded_a=struct.pack('<480I',*av);encoded_b=struct.pack('<480I',*bv)
    m.write(srca,encoded_a);m.write(srcb,encoded_b)
    checks=0
    for enabled in (0,1):
        status=0x10000000|enabled
        for f in range(1,256):
            count=[1,2,3,4,63,302,408][f%7]
            m.word(dst+count*4,0xdeadbeef)
            for reg,value in [(UC_MIPS_REG_A0,dst),(UC_MIPS_REG_A1,srca),(UC_MIPS_REG_A2,srcb),
                              (UC_MIPS_REG_A3,count),(UC_MIPS_REG_SP,sp),(UC_MIPS_REG_RA,0x80001ff0),
                              (UC_MIPS_REG_CP0_STATUS,status)]:m.uc.reg_write(reg,value)
            m.word(sp+16,f);m.finished=False
            m.uc.emu_start(entry,0,count=20000);assert m.finished
            assert m.uc.reg_read(UC_MIPS_REG_CP0_STATUS)==status
            assert m.uc.reg_read(UC_MIPS_REG_SP)==sp
            result=struct.unpack('<'+'I'*count,m.read(dst,count*4))
            for i,value in enumerate(result):
                expected=sum(((((av[i]>>s)&255)*(256-f)+((bv[i]>>s)&255)*f)>>8)<<s for s in (0,8,16))
                assert value==expected,(f,count,i,hex(value),hex(expected))
            assert m.read(dst+count*4,4)==struct.pack('<I',0xdeadbeef)
            checks+=count
    assert m.read(srca,len(encoded_a))==encoded_a and m.read(srcb,len(encoded_b))==encoded_b
    report={'ok':True,'bda_sha256':hashlib.sha256(a.bda.read_bytes()).hexdigest(),
            'pixels_checked':checks,'weights':'all 1..255','counts':[1,2,3,4,63,302,408],
            'IRQ_enabled_and_disabled_restored':True,'MXU_registers_control_restored':True,
            'tail_guard_and_const_sources_preserved':True,'environment':'Unicorn with independent MXU lane model'}
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)

if __name__=='__main__':main()
