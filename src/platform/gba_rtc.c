#include "h1_sdk.h"
#include "gba_rtc.h"
#include "diagnostics.h"
#include <libretro.h>
#include <time.h>

/* Native firmware calendar seconds use the 1970 epoch and local civil time.
 * Only read the counter; never modify the H1's clock/control/alarm registers. */
extern uint32_t h1_wall_clock(void);
extern unsigned rtc_status;
extern void *retro_get_memory_data(unsigned);
extern size_t retro_get_memory_size(unsigned);
static uint32_t saved[8];
static uint32_t clock_base, host_base, tick_base, clock_last;
static unsigned reads;
#define EPOCH_2000 946684800u
#define EPOCH_2100 4102444800u

void h1_gba_rtc_begin(void)
{
    host_base = h1_wall_clock();
    clock_base = host_base ? host_base : EPOCH_2000;
    clock_last = clock_base;
    tick_base = h1_raw_tick_80hz(); reads = 0;
    rtc_status = 0x40;
    h1_diag("RTC_BEGIN source=%s seconds=%u", host_base ? "H1" : "ticks", clock_base);
}
uint32_t h1_gba_rtc_now(void)
{
    uint32_t host = h1_wall_clock(), elapsed;
    if (host && host_base && host >= host_base) elapsed = host - host_base;
    else elapsed = (uint32_t)(h1_raw_tick_80hz() - tick_base) / 80u;
    /* A backwards system-clock correction must not rewind a running cart. */
    if (host_base && (!host || host < host_base)) {
        clock_base = clock_last;
        host_base = 0;
        tick_base = h1_raw_tick_80hz();
        elapsed = 0;
    }
    uint32_t now = clock_base + elapsed;
    if (now >= EPOCH_2000 && now < EPOCH_2100 && now < clock_last) {
        /* A correction can remain above host_base yet be below the last read. */
        clock_base = clock_last; host_base = host;
        tick_base = h1_raw_tick_80hz(); now = clock_base;
    }
    if (now < clock_base || now >= EPOCH_2100) now = EPOCH_2000;
    clock_last = now;
    if (reads++ < 3 && h1_diag_is_verbose()) h1_diag("RTC_READ seconds=%u status=%02X", now, rtc_status);
    return now;
}
static int bcd(unsigned b)
{
    if ((b & 15) > 9 || (b >> 4) > 9) return -1;
    return (int)((b >> 4) * 10 + (b & 15));
}
static int leap(int y) { return !(y % 4) && ((y % 100) || !(y % 400)); }
void h1_gba_rtc_set(uint64_t data, int full, unsigned status)
{
    static const int months[] = {31,28,31,30,31,30,31,31,30,31,30,31};
    time_t current = h1_gba_rtc_now();
    struct tm date = *localtime(&current);
    int year = date.tm_year + 1900, month = date.tm_mon + 1, day = date.tm_mday;
    if (full) {
        int yy = bcd(data & 255);
        month = bcd((data >> 8) & 255); day = bcd((data >> 16) & 255);
        if (yy < 0 || month < 1 || month > 12) return;
        year = 2000 + yy;
        if (day < 1 || day > months[month - 1] + (month == 2 && leap(year))) return;
        data >>= 32;
    }
    unsigned hb = data & 255;
    int hour = bcd(hb & 0x7f), minute = bcd((data >> 8) & 255), second = bcd((data >> 16) & 255);
    if (!(status & 0x40)) {
        if (hour < 0 || hour > 11) return;
        hour += (hb & 0x80) ? 12 : 0;
    }
    if (hour < 0 || hour > 23 || minute < 0 || minute > 59 || second < 0 || second > 59) return;
    uint32_t days = 0;
    for (int y = 1970; y < year; ++y) days += leap(y) ? 366 : 365;
    for (int m = 1; m < month; ++m) days += months[m - 1] + (m == 2 && leap(year));
    days += day - 1;
    clock_base = days * 86400u + (unsigned)hour * 3600u + (unsigned)minute * 60u + (unsigned)second;
    clock_last = clock_base;
    host_base = h1_wall_clock(); tick_base = h1_raw_tick_80hz();
    h1_diag("RTC_SET seconds=%u full=%d", clock_base, full);
}
void h1_gba_rtc_save_sync(void)
{
    saved[0] = 0x31435452u; saved[1] = 1;
    saved[2] = h1_gba_rtc_now(); saved[3] = h1_wall_clock();
    saved[4] = rtc_status & 0x6a;
    saved[5] = saved[6] = saved[7] = 0;
}
void h1_gba_rtc_save_loaded(void)
{
    if (saved[0] != 0x31435452u || saved[1] != 1 || saved[2] < EPOCH_2000 ||
        saved[2] >= EPOCH_2100 || (saved[4] & ~0x6au) || saved[5] || saved[6] || saved[7]) {
        h1_diag("RTC_RESTORE invalid payload; using H1 clock"); return;
    }
    uint32_t host = h1_wall_clock(), elapsed = 0;
    if (host && saved[3] >= EPOCH_2000 && host >= saved[3]) elapsed = host - saved[3];
    clock_base = saved[2] + elapsed;
    if (clock_base < saved[2] || clock_base >= EPOCH_2100) clock_base = EPOCH_2000;
    clock_last = clock_base;
    host_base = host; tick_base = h1_raw_tick_80hz();
    rtc_status = saved[4];
    h1_diag("RTC_RESTORE seconds=%u offline=%u status=%02X", clock_base, elapsed, rtc_status);
}
void *h1_gba_rtc_memory(unsigned id)
{
    return id == RETRO_MEMORY_RTC ? (h1_gba_rtc_enabled() ? saved : 0) : retro_get_memory_data(id);
}
size_t h1_gba_rtc_size(unsigned id)
{
    return id == RETRO_MEMORY_RTC ? (h1_gba_rtc_enabled() ? sizeof saved : 0) : retro_get_memory_size(id);
}
