#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdarg.h>
#define H1_PROFILE 1
#define H1_PROFILE_HOST_TEST 1
uint32_t h1_profile_test_clock;
static uint32_t test_wall;
static uint32_t test_raw;
static unsigned fast_clock_model, wall_reads;
uint32_t h1_profile_test_raw_tick(void)
{
    if (fast_clock_model) return (uint32_t)((uint64_t)wall_reads*80u/8000000u);
    test_raw+=20;return test_raw;
}
#include "../src/platform/profile.c"
uint32_t h1_wall_clock(void)
{
    if (fast_clock_model) {
        ++wall_reads;h1_profile_test_clock=(uint32_t)((uint64_t)wall_reads*32768u/8000000u);
        return 100u+wall_reads/8000000u;
    }
    return test_wall;
}
void h1_diag(const char *format, ...) { (void)format; }
void h1_diag_batch_begin(void) {}
void h1_diag_batch_end(void) {}
int main(void)
{
    /* Nested time is exclusive, including across Count's 32-bit wrap. */
    enabled=1;frequency=1000000;h1_profile_test_clock=UINT32_MAX-110;
    h1_profile_push(HP_CORE);h1_profile_test_clock+=100;
    h1_profile_push(HP_RENDER);h1_profile_test_clock+=40;
    h1_profile_pop();h1_profile_test_clock+=30;h1_profile_pop();
    assert(current.ticks[HP_CORE]==130 && current.ticks[HP_RENDER]==40);
    assert(!depth && !fault);
    h1_profile_video(17,23);
    h1_profile_frame(170,1);assert(current.core_sum==170 && current.displayed==1);
    assert(current.video_frames==1 && current.video_buffer_ticks==17 && current.video_scale_ticks==23);
    h1_profile_frame(17000,0);assert(current.over_budget==1);
    for (unsigned i=2;i<3900;++i) h1_profile_frame(1,0);
    assert(window_count==12 && omitted==1 && current.frames==0);
    h1_profile_dump("unit");assert(window_count==0);
    enabled=1;
    for (unsigned i=0;i<17;++i) h1_profile_push(HP_CORE);
    assert(!enabled && fault); /* No write beyond the fixed scope stack. */
    enabled=1;fault=0;frame_rtc=100;test_wall=102;
    h1_profile_frame(1,0);assert(!enabled && fault==2); /* No false fast long stall. */
    test_wall=0;
    frequency=0;h1_profile_begin();assert(!enabled); /* RTC missing: no fake us. */
    test_wall=10;h1_profile_begin();assert(!enabled && !frequency); /* Stopped clock exits bounded loop. */
    test_wall=100;h1_profile_frame(0,1);test_wall=120;h1_profile_frame(0,0);
    assert(rtc_run_frames==2 && rtc_run_displayed==1 && !rtc_run_invalid);
    assert(rtc_run_start==100 && rtc_run_last==120); /* Coarse data survives timer failure. */
    frequency=32768;h1_profile_begin();assert(!enabled && prepared && !fault);
    test_wall+=5;h1_profile_start();assert(enabled && frame_rtc==test_wall); /* Resume excludes startup. */
    h1_profile_dump("resume");assert(!enabled);
    /* Model a CPU doing >4M polling iterations before an RTC edge. The old
     * fixed limit falsely rejected this working timer. Hardware deadlines
     * must wait through the full reference second and validate it. */
    fast_clock_model=1;wall_reads=0;frequency=0;clock_attempted=0;
    h1_profile_begin();assert(!enabled && prepared && frequency==32768 && wall_reads>=16000000u);
    h1_profile_start();assert(enabled);
    h1_profile_dump("fast_cpu");fast_clock_model=0;
    puts("PASS: scopes, wrap, budget, long stall, invalid clock, resume, fast CPU calibration");
}
