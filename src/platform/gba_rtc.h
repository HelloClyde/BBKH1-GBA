#ifndef H1_GBA_RTC_H
#define H1_GBA_RTC_H
#include <stdint.h>
#include <stddef.h>
void h1_gba_rtc_begin(void);
uint32_t h1_gba_rtc_now(void);
void h1_gba_rtc_set(uint64_t data, int full, unsigned status);
void *h1_gba_rtc_memory(unsigned id);
size_t h1_gba_rtc_size(unsigned id);
void h1_gba_rtc_save_sync(void);
void h1_gba_rtc_save_loaded(void);
int h1_gba_rtc_enabled(void);
#endif
