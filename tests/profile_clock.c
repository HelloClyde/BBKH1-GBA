#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define H1_PROFILE_TCU_TEST 1
#include "../src/platform/profile_clock.h"
static uint32_t regs[64], writes;
static uint32_t samples[32];
static unsigned sample_count,sample_at,wrap_on_flag_read;
uint32_t pc_read(unsigned offset, unsigned size)
{
    if (offset>=PC_BASE && offset<PC_BASE+16) assert(!(regs[0x1c/4]&PC_BIT));
    assert(size==(offset>=PC_BASE ? 2u : offset==0x10 ? 1u : 4u));
    if (offset==PC_BASE+8 && sample_at<sample_count) return samples[sample_at++];
    if (offset==0x20 && wrap_on_flag_read) {
        wrap_on_flag_read=0;regs[0x20/4]|=PC_BIT;regs[(PC_BASE+8)/4]=5;
    }
    return regs[offset/4];
}
void pc_write(unsigned offset, uint32_t value, unsigned size)
{
    ++writes;
    if (offset>=PC_BASE && offset<PC_BASE+16) {
        assert(size==2 && !(regs[0x1c/4]&PC_BIT));
        uint32_t clock=regs[(PC_BASE+12)/4];
        if (offset==PC_BASE || offset==PC_BASE+4) assert((clock&7)==0);
        if (offset==PC_BASE+8) assert((clock&0x3f)==1);
        regs[offset/4]=value;
    } else {
        assert(value==PC_BIT || (value&~PC_IRQ_BITS)==0);
        switch (offset) {
        case 0x14: assert(size==1);regs[0x10/4]|=value;break;
        case 0x18: assert(size==1);regs[0x10/4]&=~value;break;
        case 0x28: regs[0x20/4]&=~value;break;
        case 0x2c: regs[0x1c/4]|=value;break;
        case 0x3c: regs[0x1c/4]&=~value;break;
        case 0x34: regs[0x30/4]|=value;break;
        case 0x38: regs[0x30/4]&=~value;break;
        default: assert(0);
        }
    }
}
int main(void)
{
    regs[0x10/4]=7;regs[0x1c/4]=0xfff8;regs[0x30/4]=0xa5a55a5a;regs[0x20/4]=0x10001;
    regs[PC_BASE/4]=4000;regs[PC_BASE/4+1]=2000;regs[PC_BASE/4+2]=123;regs[PC_BASE/4+3]=4;
    uint32_t original[64];memcpy(original,regs,sizeof regs);
    assert(pc_start() && pc_owned);
    assert(regs[0x10/4]==(7|PC_BIT));
    assert((regs[0x30/4]&PC_IRQ_BITS)==PC_IRQ_BITS);
    assert(regs[(PC_BASE+12)/4]==0x202);
    regs[(PC_BASE+8)/4]=65530;assert(pc_now()==65530);
    regs[(PC_BASE+8)/4]=0;assert(pc_now()==65530 && !pc_fault && pc_deferred==1);
    regs[(PC_BASE+8)/4]=5;regs[0x20/4]|=PC_BIT;assert(pc_now()==65541);
    assert(pc_wraps==1 && !(regs[0x20/4]&PC_BIT));
    /* Wrap flag observed after sampling the previous period: re-read. */
    regs[(PC_BASE+8)/4]=65534;assert(pc_now()==131070);
    wrap_on_flag_read=1;assert(pc_now()==131077 && pc_wraps==2);
    /* One corrupt read, followed by a consistent pair: no false period. */
    regs[(PC_BASE+8)/4]=8;
    samples[0]=40960;samples[1]=8;samples[2]=8;sample_at=0;sample_count=3;
    assert(pc_now()==131080 && pc_retries==1 && !pc_fault);
    /* A stale stable pair behind the previous value recovers on re-read. */
    samples[0]=7;samples[1]=7;sample_at=0;sample_count=2;
    regs[(PC_BASE+8)/4]=9;assert(pc_now()==131081 && pc_backwards==2);
    sample_count=sample_at=0;
    /* A persistent backwards counter without FULL is rejected, not wrapped. */
    regs[(PC_BASE+8)/4]=6;assert(pc_now()==131081 && pc_fault==2);
    regs[0x20/4]|=PC_IRQ_BITS;
    pc_stop();assert(!pc_owned && pc_now()==0);
    assert(memcmp(original,regs,sizeof regs)==0);
    assert(pc_start());pc_stop();assert(memcmp(original,regs,sizeof regs)==0);
    assert(pc_start());
    for (unsigned i=0;i<9;++i) samples[i]=i*10;
    sample_count=9;sample_at=0;assert(pc_now()==0 && pc_fault==1 && pc_retries==8);
    sample_count=sample_at=0;pc_stop();assert(memcmp(original,regs,sizeof regs)==0);
    assert(pc_start());regs[(PC_BASE+8)/4]=65534;assert(pc_now()==65534);
    regs[(PC_BASE+8)/4]=65;assert(pc_now()==65534 && pc_fault==2);
    pc_stop();assert(memcmp(original,regs,sizeof regs)==0);
    /* Replay the actual device's 65534 -> FULL plateau -> zero. FULL may
     * become visible while TCNT still reads the old/terminal value. */
    assert(pc_start());regs[(PC_BASE+8)/4]=65534;assert(pc_now()==65534);
    regs[0x20/4]|=PC_BIT;
    assert(pc_now()==65534 && pc_wraps==0 && (regs[0x20/4]&PC_BIT));
    regs[(PC_BASE+8)/4]=65535;
    for (unsigned i=0;i<32;++i) {
        assert(pc_now()==65535 && !pc_fault && !pc_wraps);
        assert(regs[0x20/4]&PC_BIT);
    }
    assert(pc_terminal==32);
    regs[(PC_BASE+8)/4]=0;assert(pc_now()==65536 && pc_wraps==1);
    assert(!(regs[0x20/4]&PC_BIT));
    pc_stop();assert(memcmp(original,regs,sizeof regs)==0);
    /* A read pair straddling terminal -> zero is one tick, not unstable. */
    assert(pc_start());regs[(PC_BASE+8)/4]=65534;assert(pc_now()==65534);
    samples[0]=65535;samples[1]=0;sample_count=2;sample_at=0;
    regs[(PC_BASE+8)/4]=0;regs[0x20/4]|=PC_BIT;
    assert(pc_now()==65536 && !pc_fault && !pc_retries && pc_wraps==1);
    sample_count=sample_at=0;pc_stop();assert(memcmp(original,regs,sizeof regs)==0);
    regs[0x10/4]|=PC_BIT;writes=0;assert(!pc_start() && writes==0);
    regs[0x10/4]&=~PC_BIT;regs[0x20/4]=PC_BIT;
    assert(!pc_start() && writes==0);
    regs[0x20/4]=0;regs[(PC_BASE+12)/4]=0x80;
    memcpy(original,regs,sizeof regs);assert(!pc_start());
    assert(memcmp(original,regs,sizeof regs)==0);
    puts("PASS: TCU terminal plateau, flag-before-reset, inclusive wrap, boundary race, corrupt/stale reads, bounded failure, IRQ isolation, restore/resume");
}
