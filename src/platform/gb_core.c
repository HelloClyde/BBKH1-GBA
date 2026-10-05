/* H1 adapter for pinned gnuboy. This TU is namespaced with the GB objects. */
#include "platform/core.h"
#include "platform/diagnostics.h"
#include "platform/loading.h"
#include <streams/file_stream.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#include <stdio.h>
#include "defs.h"
#include "cpu.h"
#include "hw.h"
#include "mem.h"
#include "lcd.h"
#include "regs.h"
#include "sound.h"
#include "fb.h"
#include "pcm.h"
#include "rtc.h"

struct fb fb;
struct pcm pcm;
struct rtc rtc;
int debug_trace;
unsigned h1_gb_ram_bytes;
static retro_environment_t env_cb;
static retro_video_refresh_t video_cb;
static retro_audio_sample_batch_t audio_cb;
static retro_input_poll_t poll_cb;
static retro_input_state_t input_cb;
static uint16_t pixels[160 * 144];
static byte samples[4096];
static int16_t audio_samples[4096];
static size_t ram_bytes, save_bytes;
static unsigned frame, rtc_cycles;
static int failed;

int abs(int x) { return x < 0 ? -x : x; }
void debug_disassemble(addr pc, int count) { (void)pc; (void)count; }
void vid_setpal(int i, int r, int g, int b) { (void)i; (void)r; (void)g; (void)b; }
void die(char *fmt, ...)
{
    char message[160]; va_list ap;
    va_start(ap, fmt); vsnprintf(message, sizeof(message), fmt, ap); va_end(ap);
    h1_diag("GB_CORE_ERROR %s", message);
    failed = 1; env_cb(RETRO_ENVIRONMENT_SHUTDOWN, 0);
}
int pcm_submit(void)
{
    int i;
    for (i = 0; i < pcm.pos; ++i) audio_samples[i] = ((int)pcm.buf[i] - 128) * 256;
    if (pcm.pos) audio_cb(audio_samples, (unsigned)pcm.pos / 2);
    pcm.pos = 0;
    return 1;
}
void rtc_latch(byte b)
{
    if ((rtc.latch ^ b) & b & 1) {
        rtc.regs[0] = rtc.s; rtc.regs[1] = rtc.m; rtc.regs[2] = rtc.h;
        rtc.regs[3] = rtc.d; rtc.regs[4] = (rtc.d >> 8) | (rtc.stop << 6) | (rtc.carry << 7);
    }
    rtc.latch = b;
}
void rtc_write(byte b)
{
    if (!(rtc.sel & 8)) return;
    switch (rtc.sel & 7) {
    case 0: rtc.s = b % 60; break;
    case 1: rtc.m = b % 60; break;
    case 2: rtc.h = b % 24; break;
    case 3: rtc.d = (rtc.d & 256) | b; break;
    case 4: rtc.d = (rtc.d & 255) | ((b & 1) << 8); rtc.stop = (b >> 6) & 1; rtc.carry = b >> 7; break;
    }
    rtc.regs[rtc.sel & 7] = b;
}
static void rtc_frame(void)
{
    if (!rtc.batt || rtc.stop) return;
    rtc_cycles += 70224;
    if (rtc_cycles < 4194304) return;
    rtc_cycles -= 4194304;
    if (++rtc.s < 60) return;
    rtc.s = 0;
    if (++rtc.m < 60) return;
    rtc.m = 0;
    if (++rtc.h < 24) return;
    rtc.h = 0;
    if (++rtc.d >= 512) { rtc.d = 0; rtc.carry = 1; }
}
/* RTC trailer is explicitly encoded as LE words, covered by the same save CRC.
 * Time advances with emulation; there is no unverified firmware wall-clock ABI. */
static void save_sync(void)
{
    uint32_t *p;
    if (!rtc.batt) return;
    p = (uint32_t *)((byte *)ram.sbank + ram_bytes);
    p[0] = 0x31435452; p[1] = rtc.s; p[2] = rtc.m; p[3] = rtc.h;
    p[4] = rtc.d; p[5] = rtc.stop; p[6] = rtc.carry; p[7] = rtc_cycles;
}
static void save_loaded(void)
{
    uint32_t *p;
    if (!rtc.batt) return;
    p = (uint32_t *)((byte *)ram.sbank + ram_bytes);
    if (p[0] != 0x31435452) return;
    rtc.s = p[1] % 60; rtc.m = p[2] % 60; rtc.h = p[3] % 24;
    rtc.d = p[4] & 511; rtc.stop = p[5] & 1; rtc.carry = p[6] & 1;
    rtc_cycles = p[7] % 4194304;
}
static void set_env(retro_environment_t f) { env_cb = f; }
static void set_video(retro_video_refresh_t f) { video_cb = f; }
static void set_audio(retro_audio_sample_batch_t f) { audio_cb = f; }
static void set_poll(retro_input_poll_t f) { poll_cb = f; }
static void set_input(retro_input_state_t f) { input_cb = f; }
static void init(void)
{
    enum retro_pixel_format format = RETRO_PIXEL_FORMAT_RGB565;
    env_cb(RETRO_ENVIRONMENT_SET_PIXEL_FORMAT, &format);
}
static void unload(void)
{
    free(rom.bank); free(ram.sbank);
    rom.bank = 0; ram.sbank = 0;
    ram_bytes = save_bytes = h1_gb_ram_bytes = 0; pcm.pos = 0;
}
static void deinit(void) { unload(); }
static bool load(const struct retro_game_info *game)
{
    RFILE *file;
    byte header[0x150], type, size_code;
    int64_t length;
    size_t rom_bytes, backing;
    static const unsigned ram_sizes[] = {0, 2048, 8192, 32768, 131072, 65536};
    unload();
    memset(&rom, 0, sizeof rom); memset(&ram, 0, sizeof ram);
    memset(&mbc, 0, sizeof mbc); memset(&hw, 0, sizeof hw);
    memset(&rtc, 0, sizeof rtc); memset(&bootrom, 0, sizeof bootrom);
    failed = 0; frame = rtc_cycles = 0;
    file = filestream_open(game->path, RETRO_VFS_FILE_ACCESS_READ, 0);
    if (!file) return false;
    length = filestream_get_size(file);
    if (length < 32768 || length > 8388608 || filestream_read(file, header, sizeof header) != sizeof header) goto bad_file;
    type = header[0x147]; size_code = header[0x148];
    if (size_code > 8 || header[0x149] >= sizeof ram_sizes / sizeof ram_sizes[0]) goto bad_file;
    switch (type) {
    case 0: case 8: case 9: mbc.type = MBC_NONE; break;
    case 1: case 2: case 3: mbc.type = MBC_MBC1; break;
    case 5: case 6: mbc.type = MBC_MBC2; break;
    case 15: case 16: case 17: case 18: case 19: mbc.type = MBC_MBC3; break;
    case 25: case 26: case 27: mbc.type = MBC_MBC5; break;
    case 28: case 29: case 30: mbc.type = MBC_RUMBLE; break;
    case 255: mbc.type = MBC_HUC1; break;
    default: h1_diag("GB_UNSUPPORTED_MAPPER type=%u", type); goto bad_file;
    }
    mbc.batt = type == 3 || type == 6 || type == 9 || type == 15 || type == 16 || type == 19 || type == 27 || type == 30 || type == 255;
    rtc.batt = type == 15 || type == 16;
    ram_bytes = ram_sizes[header[0x149]];
    if (mbc.type == MBC_MBC2) ram_bytes = 512;
    h1_gb_ram_bytes = ram_bytes;
    mbc.ramsize = ram_bytes > 8192 ? ram_bytes / 8192 : 1;
    mbc.romsize = 2 << size_code;
    rom_bytes = (size_t)mbc.romsize * 16384;
    if (length != (int64_t)rom_bytes) goto bad_file;
    save_bytes = (mbc.batt ? ram_bytes : 0) + (rtc.batt ? 32 : 0);
    backing = ram_bytes > 8192 ? ram_bytes : 8192;
    /* RTC follows SRAM even on timer-only carts. Keep its pointer aligned. */
    rom.bank = malloc(rom_bytes); ram.sbank = calloc(1, backing + 32);
    h1_loading_size(rom_bytes);
    if (!rom.bank || !ram.sbank) goto bad_file;
    if (filestream_seek(file, 0, RETRO_VFS_SEEK_POSITION_START) != 0 ||
        filestream_read(file, rom.bank, rom_bytes) != (int64_t)rom_bytes) goto bad_file;
    filestream_close(file);
    hw.cgb = header[0x143] == 0x80 || header[0x143] == 0xc0;
    memcpy(rom.name, header + 0x134, 15); rom.name[15] = 0;
    memset(&fb, 0, sizeof fb); memset(pixels, 0, sizeof pixels);
    fb.ptr = (byte *)pixels; fb.w = 160; fb.h = 144; fb.pitch = 320;
    fb.pelsize = 2; fb.enabled = 1;
    fb.cc[0].r = 3; fb.cc[0].l = 11; fb.cc[1].r = 2; fb.cc[1].l = 5; fb.cc[2].r = 3;
    pcm.hz = 32768; pcm.len = sizeof samples; pcm.stereo = 1; pcm.buf = samples; pcm.pos = 0;
    hw_reset(); lcd_reset(); cpu_reset(); mbc_reset(); sound_reset();
    if (type == 8 || type == 9) mbc.enableram = 1;
    REG(RI_BOOT) = 0xff; mem_updatemap(); lcd_begin(); save_sync();
    h1_diag("GB_LOAD mode=%s mapper=%u rom=%u ram=%u save=%u rtc=%d", hw.cgb ? "GBC" : "GB", type,
            (unsigned)rom_bytes, (unsigned)ram_bytes, (unsigned)save_bytes, rtc.batt);
    return true;
bad_file:
    h1_diag("GB_LOAD_FAILED size=%u", (unsigned)length);
    filestream_close(file); unload(); return false;
}
static void run_frame(void)
{
    static const unsigned ids[8] = {RETRO_DEVICE_ID_JOYPAD_RIGHT, RETRO_DEVICE_ID_JOYPAD_LEFT,
        RETRO_DEVICE_ID_JOYPAD_UP, RETRO_DEVICE_ID_JOYPAD_DOWN, RETRO_DEVICE_ID_JOYPAD_A,
        RETRO_DEVICE_ID_JOYPAD_B, RETRO_DEVICE_ID_JOYPAD_SELECT, RETRO_DEVICE_ID_JOYPAD_START};
    unsigned i, guard = 0;
    struct retro_variable skip = {"gpsp_frameskip_interval", 0};
    struct retro_variable enabled = {"gpsp_frameskip", 0};
    poll_cb();
    for (i = 0; i < 8; ++i) pad_set(1u << i, input_cb(0, RETRO_DEVICE_JOYPAD, 0, ids[i]));
    env_cb(RETRO_ENVIRONMENT_GET_VARIABLE, &enabled); env_cb(RETRO_ENVIRONMENT_GET_VARIABLE, &skip);
    fb.enabled = !enabled.value || !strcmp(enabled.value, "disabled") || frame % (skip.value && skip.value[0] == '2' ? 3 : 2) == 0;
    lcd_begin(); cpu_emulate(2280);
    while (R_LY > 0 && R_LY < 144 && !failed && ++guard < 2000) cpu_emulate(cpu.lcdc);
    if (fb.enabled && !failed) video_cb(pixels, 160, 144, 320);
    sound_mix(); pcm_submit(); rtc_frame();
    if (!(R_LCDC & 0x80)) cpu_emulate(32832);
    while (R_LY > 0 && !failed && ++guard < 2000) cpu_emulate(cpu.lcdc);
    if (guard >= 2000) die("LCD frame watchdog");
    ++frame;
}
static void av(struct retro_system_av_info *info)
{
    memset(info, 0, sizeof *info);
    info->geometry.base_width = info->geometry.max_width = 160;
    info->geometry.base_height = info->geometry.max_height = 144;
    info->geometry.aspect_ratio = 160.0f / 144.0f;
    info->timing.fps = 4194304.0 / 70224.0; info->timing.sample_rate = 32768;
}
static void *memory(unsigned type) { return type == RETRO_MEMORY_SAVE_RAM && save_bytes ? ram.sbank : 0; }
static size_t memory_size(unsigned type) { return type == RETRO_MEMORY_SAVE_RAM ? save_bytes : 0; }
/* Fixed schema at a frame boundary. Firmware/core heap pointers are rebuilt,
 * never persisted; cartridge backing includes volatile RAM as well as SRAM. */
typedef struct {
    uint32_t magic,version,backing,rom_banks,type,cgb,frames,clock_cycles;
    int model,rombank,rambank,enableram;
    struct cpu processor;
    struct hw hardware;
    struct lcd display;
    struct snd sound;
    struct rtc clock;
    byte hi[256],wram[8][4096];
    uint16_t picture[160*144];
} gb_state;
static size_t state_size(void)
{ return sizeof(gb_state)+(ram_bytes>8192?ram_bytes:8192)+32; }
static bool state_save(void *data,size_t size)
{
    if (!ram.sbank || !rom.bank || size!=state_size()) return false;
    gb_state *s=data;
    memset(s,0,sizeof *s);
    s->magic=0x31534247;s->version=1;s->backing=size-sizeof *s;
    s->rom_banks=mbc.romsize;s->type=mbc.type;s->cgb=hw.cgb;
    s->frames=frame;s->clock_cycles=rtc_cycles;
    s->model=mbc.model;s->rombank=mbc.rombank;s->rambank=mbc.rambank;s->enableram=mbc.enableram;
    s->processor=cpu;s->hardware=hw;s->display=lcd;s->sound=snd;s->clock=rtc;
    memcpy(s->hi,ram.hi,sizeof s->hi);memcpy(s->wram,ram.ibank,sizeof s->wram);
    memcpy(s->picture,pixels,sizeof pixels);memcpy(s+1,ram.sbank,s->backing);
    return true;
}
static bool state_load(const void *data,size_t size)
{
    const gb_state *s=data;
    if (!ram.sbank || size!=state_size() || s->magic!=0x31534247 || s->version!=1 ||
        s->backing!=size-sizeof *s || s->rom_banks!=(unsigned)mbc.romsize || s->type!=(unsigned)mbc.type ||
        s->cgb!=(unsigned)hw.cgb || s->hardware.cgb!=hw.cgb ||
        s->rombank<0 || s->rombank>=mbc.romsize || s->rambank<0 || s->rambank>=mbc.ramsize ||
        s->processor.speed<0 || s->processor.speed>1 || s->clock_cycles>=4194304 ||
        s->clock.s<0 || s->clock.s>=60 || s->clock.m<0 || s->clock.m>=60 ||
        s->clock.h<0 || s->clock.h>=24 || s->clock.d<0 || s->clock.d>=512) return false;
    cpu=s->processor;hw=s->hardware;lcd=s->display;snd=s->sound;rtc=s->clock;
    mbc.model=s->model;mbc.rombank=s->rombank;mbc.rambank=s->rambank;mbc.enableram=s->enableram;
    frame=s->frames;rtc_cycles=s->clock_cycles;
    memcpy(ram.hi,s->hi,sizeof s->hi);memcpy(ram.ibank,s->wram,sizeof s->wram);
    memcpy(pixels,s->picture,sizeof pixels);memcpy(ram.sbank,s+1,s->backing);
    pcm.pos=0;failed=0;mem_updatemap();vram_dirty();pal_dirty();lcd_begin();
    return true;
}
const h1_core h1_gb_core = {"GB/GBC", set_env, set_video, set_audio, set_poll, set_input,
    init, deinit, load, unload, run_frame, av, memory, memory_size, save_loaded, save_sync, state_size, state_save, state_load};
