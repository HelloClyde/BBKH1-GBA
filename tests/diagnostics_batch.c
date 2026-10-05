#include "h1_sdk.h"
#include <assert.h>
#include <string.h>
#include "../src/platform/diagnostics.c"

static char disk[LOG_LIMIT+1024],reference[LOG_LIMIT+1024];
static size_t disk_size,position;
static unsigned opens,closes,writes,opened;
static int fail_open,fail_write,fail_close;
h1_file *h1_fopen(const char *path,const char *mode)
{
    assert(!strcmp(path,H1_LOG_PATH));
    if (fail_open && strcmp(mode,"wb")) return 0;
    assert(!opened);opened=1;++opens;
    if (!strcmp(mode,"wb")) disk_size=0;
    position=0;return (h1_file *)(void *)disk;
}
int h1_fclose(h1_file *f)
{ assert(f==(h1_file *)(void *)disk && opened);opened=0;++closes;return fail_close ? -1 : 0; }
int h1_fseek(h1_file *f,int offset,int whence)
{ assert(f && opened && !offset && whence==H1_SEEK_END);position=disk_size;return (int)position; }
h1_size_t h1_fwrite(const void *data,h1_size_t size,h1_size_t count,h1_file *f)
{
    size_t n=(size_t)size*count;
    assert(f && opened);++writes;
    if (fail_write) n/=2;
    assert(position+n<=sizeof disk);
    memcpy(disk+position,data,n);position+=n;disk_size=position;return (h1_size_t)n;
}
static void init(void)
{ fail_open=fail_write=fail_close=0;assert(h1_diag_init());opens=closes=writes=0; }
static void records(void)
{
    for (unsigned i=0;i<180;++i)
        h1_diag("PROFILE_COST window=%u name=screen_output ticks=1116941 us=34086334 calls=300 text=%080u",i,i);
}
int main(void)
{
    init();h1_diag("HEAD");records();h1_diag("TAIL");
    size_t expected=disk_size;memcpy(reference,disk,expected);
    unsigned ordinary_opens=opens;assert(ordinary_opens==182 && opens==closes);
    init();h1_diag("HEAD");
    /* Stage records commit before any potentially blocking hardware call. */
    assert(!opened && disk_size && strstr(disk,"HEAD"));
    h1_diag_batch_begin();h1_diag_batch_begin();records();
    assert(!opened && batch_used && opens==closes);
    size_t before=disk_size;h1_diag_batch_end();assert(disk_size==before);
    h1_diag_batch_end();h1_diag("TAIL");
    assert(!opened && !batch_used && disk_size==expected && !memcmp(disk,reference,expected));
    assert(opens==closes && opens<ordinary_opens/10);
    printf("PASS: identical ordered records; %u ordinary opens reduced to %u batched opens\n",ordinary_opens,opens);
    h1_diag_batch_end();assert(active); /* Unmatched end is harmless. */
    init();h1_diag("KEEP");before=disk_size;fail_open=1;
    h1_diag_batch_begin();h1_diag("FAILED");h1_diag_batch_end();
    assert(!active && !opened && !batch_used && disk_size==before && strstr(disk,"KEEP"));
    init();h1_diag("KEEP");fail_write=1;
    h1_diag_batch_begin();h1_diag("FAILED");h1_diag_batch_end();
    assert(!active && !opened && !batch_used);before=disk_size;
    h1_diag("IGNORED");assert(disk_size==before);
    init();fail_close=1;h1_diag_batch_begin();h1_diag("CLOSE_FAILED");h1_diag_batch_end();
    assert(!active && !opened && !batch_used);
    init();disk_size=LOG_LIMIT-5;h1_diag("LIMIT");
    assert(!active && !opened && disk_size==LOG_LIMIT-5);
    puts("PASS: update-open/short-write/close failures preserve prior log, close handles and disable logging; bounded size");
}
