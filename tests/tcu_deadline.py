"""Compile the actual patched QEMU scheduler in a controlled clock harness."""
import os,shutil,subprocess
from pathlib import Path
root=Path(__file__).resolve().parents[1]
source=(root/'.tools/h1-emulator/qemu/overlay/hw/timer/jz4740_tcu.c').read_text()
schedule=source[source.index('static void tcu_schedule('):source.index('static void tcu_raise_pending(')]
harness=r'''
#include <stdint.h>
#include <stdbool.h>
#include <assert.h>
#include <stdio.h>
#define JZ4740_TCU_CHANNELS 1
#define TCU_HALF_SHIFT 16
#define QEMU_CLOCK_VIRTUAL 0
typedef struct { int64_t deadline_ns[1],half_deadline_ns[1];unsigned pending_mask,running;void *timer; } JZ4740TCUState;
static int64_t now,armed;
static unsigned recomputes;
static int64_t qemu_clock_get_ns(int ignored) { (void)ignored;return now; }
static int tcu_counter_running(JZ4740TCUState *s,unsigned ch) { (void)ch;return s->running; }
static int64_t tcu_next_deadline_ns(JZ4740TCUState *s,unsigned ch,int half,int64_t t) {
    (void)s;(void)ch;++recomputes;return t+(half ? 50 : 100);
}
static void timer_del(void *timer) { (void)timer;armed=0; }
static void timer_mod(void *timer,int64_t time) { (void)timer;armed=time; }
'''
main=r'''
int main(void) {
    JZ4740TCUState s={0};s.running=1;tcu_schedule(&s);
    assert(s.deadline_ns[0]==100 && s.half_deadline_ns[0]==50 && armed==50);
    for (now=1;now<50;++now) tcu_schedule(&s);
    assert(recomputes==2 && s.deadline_ns[0]==100 && armed==50);
    s.pending_mask=1u<<16;now=50;tcu_schedule(&s);
    assert(s.deadline_ns[0]==100 && !s.half_deadline_ns[0] && armed==100);
    for (now=51;now<100;++now) tcu_schedule(&s);
    assert(s.deadline_ns[0]==100 && recomputes==2);
    s.pending_mask|=1;now=100;tcu_schedule(&s);assert(!armed);
    s.pending_mask=0;s.deadline_ns[0]=s.half_deadline_ns[0]=0;
    tcu_schedule(&s);assert(s.deadline_ns[0]==200 && armed==150);
    s.running=0;tcu_schedule(&s);assert(!armed && !s.deadline_ns[0]);
    s.running=1;now=1000;tcu_schedule(&s);assert(s.deadline_ns[0]==1100 && armed==1050);
    puts("PASS: actual QEMU TCU scheduler preserves pending matches across unrelated writes, handles flags and restart");
}
'''
out=root/'build/profile-unit/tcu-deadline.c';out.write_text(harness+schedule+main)
exe=out.with_suffix('.exe')
gcc=os.environ.get('HOST_CC') or shutil.which('gcc')
if not gcc:raise SystemExit('HOST_CC or gcc is required')
subprocess.run([gcc,'-std=c11','-Wall','-Wextra',str(out),'-o',str(exe)],check=True)
subprocess.run([str(exe)],check=True)
