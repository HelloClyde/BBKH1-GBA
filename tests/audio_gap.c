#include <assert.h>
#include <stdint.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#define H1_PROFILE 1
#define H1_RUNTIME_SYS_TABLE_SLOT 0
void *h1_runtime_entry(void *,unsigned);
void *h1_runtime_table(unsigned);
uint32_t h1_raw_tick_80hz(void);
#include "../src/platform/audio.c"
void *h1_runtime_entry(void *table,unsigned offset) { (void)table;(void)offset;return 0; }
void *h1_runtime_table(unsigned slot) { (void)slot;return 0; }
int h1_diag_is_verbose(void) { return 0; }
static uint32_t reset_elapsed;
uint32_t h1_raw_tick_80hz(void) { return batches*2+reset_elapsed; }
uint32_t h1_wall_clock(void) { return 100+batches; }
static unsigned logs,events;
void h1_diag_batch_begin(void) {}
void h1_diag_batch_end(void) {}
void h1_diag(const char *format,...)
{
    char line[512];va_list args;va_start(args,format);
    vsnprintf(line,sizeof line,format,args);va_end(args);++logs;
    if (strncmp(line,"AUDIO_GAP ",10)==0) {
        unsigned batch,rtc,tick,q,c,missing,old_pos,new_pos,reset;
        assert(sscanf(line,"AUDIO_GAP batch=%u rtc=%u raw_tick=%u queued=%u consumed=%u missing=%u old_position=%u new_position=%u reset_ticks=%u",
            &batch,&rtc,&tick,&q,&c,&missing,&old_pos,&new_pos,&reset)==9);
        assert(batch==5+events && rtc==100+batch && tick==batch*2);
        assert(q==100 && c==300 && missing==200 && old_pos==10 && new_pos==310);
        assert(reset==3);
        ++events;
    } else assert(strcmp(line,"AUDIO_GAPS reason=pause count=16 omitted=4 total=20")==0);
}
int main(void)
{
    queued=100;read_position=10;
    for (batches=1;batches<=20;++batches) {
        reset_elapsed=0;record_gap(300,310);reset_elapsed=3;finish_gap();
    }
    assert(logs==0 && gap_count==20 && gap_total==20);
    dump_gaps("pause");assert(logs==17 && events==16 && gap_count==0 && gap_total==20);
    batches=0x7fffffffu;reset_elapsed=0;record_gap(300,310);
    reset_elapsed=3;finish_gap();assert(gaps[0].reset_ticks==3 && logs==17);
    puts("PASS: audio gap events stay in RAM, retain last 16 in order, preserve deficit and cumulative count");
}
