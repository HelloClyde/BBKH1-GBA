/* Exercise the actual profiler with a 16-bit physical-style TCU: FULL is a
 * readable plateau and FULL flag is raised before reset on the next tick.
 * The older QEMU counter model does not expose this terminal sample. */
#include <assert.h>
#include <stdint.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#define H1_PROFILE 1
#define H1_PROFILE_TCU_TEST 1
uint32_t h1_raw_tick_80hz(void);
#include "../src/platform/profile.c"
static uint32_t registers[64];
static uint64_t model_ticks,base_ticks,next_full;
static unsigned calibrated;
void h1_diag_batch_begin(void) {}
void h1_diag_batch_end(void) {}
static int running(void) {
    return (registers[0x10/4]&PC_BIT) && (registers[(PC_BASE+12)/4]&7u)==2u;
}
static void flags(void) {
    if (!running()) return;
    uint64_t elapsed=model_ticks-base_ticks;
    if (elapsed>=next_full) {
        registers[0x20/4]|=PC_BIT;
        do { next_full+=65536; } while (elapsed>=next_full);
    }
}
uint32_t pc_read(unsigned offset,unsigned size) {
    (void)size;flags();
    if (offset==PC_BASE+8 && running()) return (uint32_t)(model_ticks-base_ticks)&65535;
    return registers[offset/4];
}
void pc_write(unsigned offset,uint32_t value,unsigned size) {
    (void)size;
    if (offset>=PC_BASE && offset<PC_BASE+16) {
        registers[offset/4]=value;
        if (offset==PC_BASE+8) { base_ticks=model_ticks-value;next_full=65535; }
        return;
    }
    switch (offset) {
    case 0x14: registers[0x10/4]|=value;break;
    case 0x18: registers[0x10/4]&=~value;break;
    case 0x28: registers[0x20/4]&=~value;break;
    case 0x2c: registers[0x1c/4]|=value;break;
    case 0x3c: registers[0x1c/4]&=~value;break;
    case 0x34: registers[0x30/4]|=value;break;
    case 0x38: registers[0x30/4]&=~value;break;
    default: assert(0);
    }
}
uint32_t h1_wall_clock(void) { ++model_ticks;return 100+(uint32_t)(model_ticks/32768); }
uint32_t h1_raw_tick_80hz(void) { return (uint32_t)(model_ticks*40/32768); }
void h1_diag(const char *format,...) {
    char line[1024];va_list args;va_start(args,format);
    vsnprintf(line,sizeof line,format,args);va_end(args);
    if (strstr(line,"PROFILE_CLOCK source=TCU5_RTC") && strstr(line,"ready=1")) ++calibrated;
    /* Actual user log shows ~7000 RTC ticks per diagnostic file write. */
    model_ticks+=6950;
}
static void frames(unsigned count) {
    for (unsigned i=0;i<count;++i) {
        h1_profile_push(HP_CORE);model_ticks+=548;h1_profile_pop();
        h1_profile_push(HP_OTHER);model_ticks+=2;h1_profile_pop();
        h1_profile_frame(548,!(i&1));
        assert(enabled && !fault && !pc_fault);
    }
}
int main(void) {
    registers[0x10/4]=7;registers[0x1c/4]=0xfff8;
    registers[0x30/4]=0xa5a55a5a;registers[0x20/4]=0x10001;
    registers[PC_BASE/4]=7549;registers[PC_BASE/4+1]=24911;
    registers[PC_BASE/4+2]=8986;registers[PC_BASE/4+3]=0;
    uint32_t before[64];memcpy(before,registers,sizeof before);
    h1_profile_begin();
    assert(!enabled && prepared && frequency==32768 && calibrated==1);
    assert(pc_terminal>0 && !pc_fault);
    assert(!pc_owned && memcmp(before,registers,sizeof before)==0);
    /* Startup file writes and audio initialization span multiple wraps.
     * They must not invalidate frame one or enter its cost accounting. */
    model_ticks+=5*32768;
    h1_profile_push(HP_AUDIO);model_ticks+=100;h1_profile_pop();
    h1_profile_start();assert(enabled && pc_owned && pc_total<=1);
    frames(300);assert(window_count==1 && pc_wraps>=2);
    assert(windows[0].ticks[HP_CORE]==300*548);
    assert(windows[0].ticks[HP_OTHER]==300*2 && !windows[0].ticks[HP_AUDIO]);
    h1_profile_dump("pause");assert(!pc_owned && !fault);
    assert(memcmp(before,registers,sizeof before)==0);
    model_ticks+=12*32768;h1_profile_begin();assert(!enabled && prepared && calibrated==2);
    model_ticks+=5*32768;h1_profile_start();assert(enabled && pc_total<=1);
    frames(300);h1_profile_dump("exit");assert(!pc_owned && !fault);
    assert(memcmp(before,registers,sizeof before)==0);
    h1_profile_begin();h1_profile_start();model_ticks+=3*32768;
    h1_profile_frame(0,0);assert(!enabled && fault==2 && fault_frame==1);
    assert(fault_current_rtc-fault_previous_rtc>=3);
    h1_profile_dump("stalled");assert(memcmp(before,registers,sizeof before)==0);
    h1_profile_begin();assert(prepared && !pc_owned);
    /* Audio/OS may claim TCU5 after calibration. Never steal that channel. */
    registers[0x10/4]|=PC_BIT;
    uint32_t busy[64];memcpy(busy,registers,sizeof busy);
    h1_profile_start();assert(!enabled && !pc_owned && fault==4);
    h1_profile_dump("busy");assert(memcmp(busy,registers,sizeof busy)==0);
    puts("PASS: physical terminal calibration, slow startup/resume excluded, exact exclusive costs, runtime stall rejected and exact restoration");
}
