#include "h1_sdk.h"
#include "platform/frontend.h"
#include "platform/core.h"
#include "platform/save.h"
#include "platform/file_selector.h"
#include "platform/diagnostics.h"
#include "platform/gui_context.h"
#include "platform/game_video.h"
#include "platform/audio.h"
#include "platform/gba_rtc.h"
#include "platform/loading.h"
#include "platform/menu.h"
#include "platform/profile.h"
#ifdef H1_JIT
#include "platform/jit.h"
#endif
#include <libretro.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static const h1_core gba_core = {"GBA", retro_set_environment, retro_set_video_refresh,
    retro_set_audio_sample_batch, retro_set_input_poll, retro_set_input_state,
    retro_init, retro_deinit, retro_load_game, retro_unload_game, retro_run,
    retro_get_system_av_info, h1_gba_rtc_memory, h1_gba_rtc_size, h1_gba_rtc_save_loaded, h1_gba_rtc_save_sync, retro_serialize_size, retro_serialize, retro_unserialize};
static const h1_core *core;
static input_state input;
static uint16_t *screen;
static unsigned frames, total_frames, videos, video_errors;
static unsigned video_callbacks, input_callbacks;
static int variable_changed, profile_waiting;
typedef struct { unsigned frame,video,errors,ms; } heartbeat_record;
static heartbeat_record heartbeats[8];
static unsigned heartbeat_count,heartbeat_omitted;
static void remember_heartbeat(unsigned ms)
{
    if (heartbeat_count==8) {
        memmove(heartbeats,heartbeats+1,7*sizeof *heartbeats);
        --heartbeat_count;++heartbeat_omitted;
    }
    heartbeats[heartbeat_count++]=(heartbeat_record){total_frames,videos,video_errors,ms};
}
static void dump_heartbeats(void)
{
    if (!heartbeat_count) return;
    h1_diag_batch_begin();
    h1_diag("HEARTBEAT_DUMP count=%u omitted=%u",heartbeat_count,heartbeat_omitted);
    for (unsigned i=0;i<heartbeat_count;++i) {
        heartbeat_record *p=&heartbeats[i];
        h1_diag("FRAME_HEARTBEAT n=%u video=%u errors=%u ms=%u deferred=1",p->frame,p->video,p->errors,p->ms);
    }
    h1_diag_batch_end();heartbeat_count=heartbeat_omitted=0;
}
#ifndef H1_TEST_FRAMES
#define H1_TEST_FRAMES 0
#endif

static void log_line(const char *line)
{
    h1_diag("%s", line);
}
static void core_log(enum retro_log_level level, const char *fmt, ...)
{
    char line[192]; va_list args;
    if (level < RETRO_LOG_WARN && !h1_diag_is_verbose()) return;
    va_start(args, fmt); vsnprintf(line, sizeof(line), fmt, args); va_end(args);
    log_line(line);
}
static const char *option(const char *key)
{
    if (!strcmp(key, "gpsp_bios")) return "builtin";
    if (!strcmp(key, "gpsp_boot_mode")) return "game";
    if (!strcmp(key, "gpsp_drc")) {
#ifdef H1_JIT
        return h1_jit_ready() ? "enabled" : "disabled";
#else
        return "disabled";
#endif
    }
    if (!strcmp(key, "gpsp_rtc")) return "auto";
    if (!strcmp(key, "gpsp_serial") || !strcmp(key, "gpsp_rumble") ||
        !strcmp(key, "gpsp_color_correction") || !strcmp(key, "gpsp_frame_mixing") ||
        !strcmp(key, "gpsp_sprlim")) return "disabled";
    if (!strcmp(key, "gpsp_frameskip")) return input.skip ? "fixed_interval" : "disabled";
    if (!strcmp(key, "gpsp_frameskip_interval")) return input.skip == 2 ? "2" : "1";
    if (!strcmp(key, "gpsp_frameskip_threshold")) return "33";
    if (!strcmp(key, "gpsp_turbo_period")) return "4";
    return 0;
}
static bool environment(unsigned cmd, void *data)
{
    switch (cmd) {
    case RETRO_ENVIRONMENT_GET_LOG_INTERFACE: ((struct retro_log_callback *)data)->log = core_log; return true;
    case RETRO_ENVIRONMENT_GET_CORE_OPTIONS_VERSION: *(unsigned *)data = 1; return true;
    case RETRO_ENVIRONMENT_GET_LANGUAGE: *(unsigned *)data = RETRO_LANGUAGE_ENGLISH; return true;
    case RETRO_ENVIRONMENT_GET_INPUT_BITMASKS: return true;
    case RETRO_ENVIRONMENT_SET_PIXEL_FORMAT: return *(enum retro_pixel_format *)data == RETRO_PIXEL_FORMAT_RGB565;
    case RETRO_ENVIRONMENT_SET_CORE_OPTIONS:
    case RETRO_ENVIRONMENT_SET_CORE_OPTIONS_INTL:
    case RETRO_ENVIRONMENT_SET_INPUT_DESCRIPTORS:
    case RETRO_ENVIRONMENT_SET_MEMORY_MAPS:
    case RETRO_ENVIRONMENT_SET_MINIMUM_AUDIO_LATENCY: return true;
    case RETRO_ENVIRONMENT_GET_SYSTEM_DIRECTORY:
    case RETRO_ENVIRONMENT_GET_SAVE_DIRECTORY: *(const char **)data = GBA_ROOT; return true;
    case RETRO_ENVIRONMENT_GET_VARIABLE: {
        struct retro_variable *v = (struct retro_variable *)data;
        v->value = option(v->key); return v->value != 0;
    }
    case RETRO_ENVIRONMENT_GET_VARIABLE_UPDATE: *(bool *)data = variable_changed; variable_changed = 0; return true;
    case RETRO_ENVIRONMENT_SHUTDOWN: input.exit_requested = 1; return true;
    default: return false;
    }
}
static void video_impl(const void *data, unsigned w, unsigned h, size_t pitch)
{
    static volatile uint32_t *last_buffer;
    int trace = video_callbacks++ < 6 && h1_diag_is_verbose();
    int blit_rc, present_rc;
    if (trace) h1_diag("VIDEO_CB_BEGIN frame=%u data=%p width=%u height=%u pitch=%u", total_frames + 1, data, w, h, (unsigned)pitch);
    if (!data) { if (trace) h1_diag("VIDEO_CB_DUPLICATE"); return; }
    if (!((w == 240 && h == 160) || (w == 160 && h == 144)) || pitch < w * 2) { ++video_errors; return; }
    if (trace) h1_diag("VIDEO_SCALE_BEGIN");
    uint32_t buffer_start=h1_profile_now();
    volatile uint32_t *buffer=gba_game_buffer(trace);
    if (!buffer) { ++video_errors; return; }
    uint32_t scale_start=h1_profile_now();
    scale_frame_rgb32((uint32_t *)buffer,data,pitch,input.scale,w,h,input.scale_changed||!videos||last_buffer!=buffer);
    h1_profile_video(scale_start-buffer_start,h1_profile_now()-scale_start);
    last_buffer=buffer;
    input.scale_changed=0;
    if (trace) h1_diag("VIDEO_SCALE_END");
    /* Full packed framebuffer, including black borders. */
    if (trace) h1_diag("VIDEO_BLIT_BEGIN");
    blit_rc = 0;
    if (trace) h1_diag("VIDEO_BLIT_END rc=%d", blit_rc);
    if (trace) h1_diag("VIDEO_PRESENT_BEGIN");
    present_rc = blit_rc;
    if (trace) h1_diag("VIDEO_PRESENT_END rc=%d", present_rc);
    if (blit_rc < 0 || present_rc < 0) ++video_errors;
    ++videos;
}
static void video(const void *data, unsigned w, unsigned h, size_t pitch)
{ h1_profile_push(HP_VIDEO); video_impl(data,w,h,pitch); h1_profile_pop(); }
static size_t audio(const int16_t *data, size_t n)
{ h1_profile_push(HP_AUDIO); size_t rc=gba_audio_write(data,n); h1_profile_pop(); return rc; }
static void poll(void)
{
    int trace = input_callbacks++ < 6 && h1_diag_is_verbose();
    if (trace) h1_diag("INPUT_POLL_BEGIN frame=%u", total_frames + 1);
    h1_profile_push(profile_waiting ? HP_WAIT : HP_INPUT); input_poll(&input); h1_profile_pop();
    if (trace) h1_diag("INPUT_POLL_END mask=%u exit=%d menu=%d", input.mask, input.exit_requested, input.menu_requested);
    if (input.skip_changed) { variable_changed = 1; input.skip_changed = 0; }
}
static int16_t buttons(unsigned port, unsigned device, unsigned index, unsigned id)
{
    if (input.pause_requested || port || index || device != RETRO_DEVICE_JOYPAD) return 0;
    if (id == RETRO_DEVICE_ID_JOYPAD_MASK) return input.mask;
    return id < 16 ? ((input.mask >> id) & 1u) : 0;
}
static void clear_input(int trace)
{
    /* Consume selector confirmation so it cannot become an in-game held key. */
    input_state discard;
    if (trace) h1_diag("INPUT_CLEAR_BEGIN");
    memset(&discard, 0, sizeof(discard)); input_poll(&discard);
    if (trace) h1_diag("INPUT_CLEAR_END");
    memset(input.held, 0, sizeof(input.held)); input.mask = 0;
    input.exit_requested = input.menu_requested = input.pause_requested = 0;
}
int h1_app_main(void)
{
    char directory[H1_ROM_PATH_MAX] = GBA_ROOT;
    int result = 0;
    int logging;
    logging = h1_diag_init();
#if H1_PROFILE
    h1_diag("PROFILE_BUILD version=0.12.3 clock=TCU5_RTC init=manual_8_4_4 read=terminal_inclusive start=game_loop dump=batch8k video=split scaler=linear_MXU1_Q8_split4 heartbeat=deferred input=GUI_9D8");
#endif
#ifdef H1_JIT
    h1_diag("APP_BEGIN version=0.12.3 diagnostics=1 core=JIT audio=PCM rtc=auto input=GUI_9D8");
#else
    h1_diag("APP_BEGIN version=0.12.3 diagnostics=1 core=interpreter audio=PCM rtc=auto input=GUI_9D8");
#endif
    if (!logging) h1_message_box(0, "Cannot create A:\\GBA\\h1gba.log. Create the GBA directory and check writable storage.", "H1 GBA log", 0);
    extern int h1_linear_init(void);
    h1_diag("LINEAR_BACKEND name=MXU1_Q8 selftest=%d irq_scope=cached_row state=preserved",h1_linear_init());
    memset(&input, 0, sizeof(input)); input.scale = 1; input.skip = 1;
    h1_diag("SCREEN_ALLOC_BEGIN bytes=%u", 480u * 272u * 2u);
    screen = (uint16_t *)malloc(480 * 272 * 2);
    h1_diag("SCREEN_ALLOC_END ptr=%p", screen);
    if (!screen) { h1_message_box(0, "Not enough memory", "H1 GBA", 0); return 1; }
    for (;;) {
        char path[H1_ROM_PATH_MAX], line[160];
        struct retro_game_info game;
        save_store store, rtc_store;
        h1_config config;
        void *save, *rtc_save;
        size_t save_size, rtc_size;
        uint32_t start, saved_at, rtc_saved_at, load_tick, heartbeat_tick;
        int pick, load_status, save_enabled, rtc_enabled;
        h1_diag_verbose(1);
        h1_diag("ROM_SELECT_BEGIN dir=%s", directory);
        pick = h1_select_rom(directory, path, sizeof(path));
        h1_diag("ROM_SELECT_END status=%d", pick);
        if (pick == 0) {
            log_line("ROM selection cancelled");
            /* V1.41's selector sets game display mode even on cancellation.
             * Closing without an open context is a no-op, so pair the native
             * window APIs to restore desktop redraw before returning. */
            h1_diag("SELECTOR_CANCEL_RESTORE_BEGIN");
            if (gba_gui_open()) gba_gui_close();
            else result = 4;
            h1_diag("SELECTOR_CANCEL_RESTORE_END restored=%d", result == 0);
            break;
        }
        if (pick < 0) {
            h1_message_box(0, "File selection failed or path is too long. Please select a .gba, .gb or .gbc ROM.", "H1 GBA", 0);
            clear_input(1); continue;
        }
        {
            size_t n = strlen(path);
            core = n >= 4 && (path[n-1] == 'a' || path[n-1] == 'A') ? &gba_core : &h1_gb_core;
        }
        h1_config_load(&config,&input,path);
        h1_diag("CORE_SELECTED name=%s", core->name);
        core->environment(environment); core->video(video); core->audio(audio); core->poll(poll); core->input(buttons);
        h1_rom_directory(path, directory, sizeof(directory));
        h1_diag("ROM_PATH length=%u path=%s", (unsigned)strlen(path), path);
        h1_diag_hex("ROM_PATH_HEX", path, strlen(path));
        if (!gba_gui_open()) {
            h1_message_box(0, "Cannot initialize the native graphics window.", "H1 GBA", 0);
            result = 4; break;
        }
        clear_input(1);load_tick=h1_raw_tick_80hz();
        h1_diag("LOADING_BEGIN");h1_loading_begin(screen);
        frames = total_frames = videos = video_errors = video_callbacks = input_callbacks = 0; variable_changed = 0;
        h1_diag("CORE_INIT_BEGIN");
        core->init();
        h1_diag("CORE_INIT_END");
        h1_loading_step(20,"READING ROM");
        memset(&game, 0, sizeof(game)); game.path = path;
        log_line(path);
        h1_diag("ROM_LOAD_BEGIN");
        pick = core->load(&game);
        h1_diag("ROM_LOAD_END loaded=%d", pick);
#ifdef H1_JIT
        if (core == &gba_core) h1_jit_report();
#endif
        if (!pick) {
            h1_loading_end();h1_diag("LOADING_DONE failed=1");
            core->deinit(); gba_gui_close();
            h1_message_box(0, "ROM load failed. Check file and free memory.", "H1 GBA", 0);
            clear_input(1); continue;
        }
        h1_loading_step(75,"RESTORING SAVE");
        save = core->memory(RETRO_MEMORY_SAVE_RAM); save_size = core->memory_size(RETRO_MEMORY_SAVE_RAM);
        h1_diag("SAVE_LOAD_BEGIN ptr=%p bytes=%u", save, (unsigned)save_size);
        memset(&store, 0, sizeof store); store.slot = -1;
        load_status = save && save_size ? save_load(&store, path, save, save_size) : 0;
        if (core == &h1_gb_core && core->save_loaded && load_status == 1) core->save_loaded();
        h1_diag("SAVE_LOAD_END status=%d slot=%d generation=%u", load_status, store.slot, store.generation);
        save_enabled = save && save_size && load_status >= 0;
        if (load_status < 0) h1_message_box(0, "Save cannot be restored. Existing files are preserved; saving is disabled for this session.", "H1 GBA", 0);
        log_line(load_status == 1 ? "SAVE restored" : load_status == 0 ? "SAVE new" : "SAVE restore failed");
        rtc_save = core->memory(RETRO_MEMORY_RTC); rtc_size = core->memory_size(RETRO_MEMORY_RTC);
        rtc_enabled = 0;
        if (rtc_save && rtc_size) {
            core->save_sync();
            int restored = save_load_rtc(&rtc_store, path, rtc_save, rtc_size);
            rtc_enabled = restored >= 0;
            if (restored == 1) core->save_loaded();
            h1_diag("RTC_SAVE_LOAD status=%d bytes=%u", restored, (unsigned)rtc_size);
            if (restored < 0) h1_message_box(0, "RTC state cannot be restored. Existing RTC files are preserved; clock uses H1 time.", "H1 GBA", 0);
        }
        heartbeat_count=heartbeat_omitted=0;
#if H1_PROFILE
        h1_diag("PROFILE_SETTINGS scale=%d skip=%d sound=%d",input.scale,input.skip,config.sound);
#endif
        h1_profile_begin();
        h1_loading_step(95,"STARTING AUDIO");
        {
            struct retro_system_av_info av;core->av(&av);
            if (!H1_BENCHMARK && config.sound) gba_audio_open((unsigned)av.timing.sample_rate);
        }
        h1_loading_step(100,"READY");h1_loading_end();
        h1_diag("LOADING_DONE ticks=%u",(unsigned)(h1_raw_tick_80hz()-load_tick));
        h1_diag("TIMER_START_BEGIN"); h1_timer_start(); h1_diag("TIMER_START_END");
        h1_diag("TIMER_READ_BEGIN"); start = h1_timer_read_ms(); h1_diag("TIMER_READ_END ms=%u", start); saved_at = start;
        rtc_saved_at=heartbeat_tick=h1_raw_tick_80hz();
        h1_profile_start();
        while (!input.exit_requested && !input.menu_requested) {
            uint32_t now;
            if (input.pause_requested) {
                gba_audio_pause();h1_timer_stop();h1_profile_dump("pause");
                dump_heartbeats();
                int action=h1_pause_menu(&input,&config,core,path,screen);
                clear_input(0);
                if (action) {
                    input.menu_requested=action==1;input.exit_requested=action==2;break;
                }
                if (input.skip_changed) { variable_changed=1;input.skip_changed=0; }
#if H1_PROFILE
                h1_diag("PROFILE_SETTINGS scale=%d skip=%d sound=%d",input.scale,input.skip,config.sound);
#endif
                h1_profile_begin();
                if (!H1_BENCHMARK && config.sound) {
                    if (!gba_audio_resume()) {
                        struct retro_system_av_info av;core->av(&av);gba_audio_open((unsigned)av.timing.sample_rate);
                    }
                } else gba_audio_close();
                h1_timer_start();start=saved_at=h1_timer_read_ms();frames=0;
                rtc_saved_at=heartbeat_tick=h1_raw_tick_80hz();
                h1_profile_start();
            }
            int trace = total_frames < 10 && h1_diag_is_verbose();
            if (trace) h1_diag("FRAME_BEGIN n=%u video=%u", total_frames + 1, videos);
            unsigned profile_videos=videos;
            h1_profile_push(HP_INPUT);input_frame(&input);h1_profile_pop();
            uint32_t profile_start=h1_profile_now();
            h1_profile_push(HP_CORE);
            core->run();
            h1_profile_pop();
            uint32_t profile_core=h1_profile_now()-profile_start;
            h1_profile_push(HP_OTHER);
            ++frames; ++total_frames;
            if (trace) h1_diag("FRAME_END n=%u video=%u errors=%u", total_frames, videos, video_errors);
            if (total_frames == 10) h1_diag_verbose(0);
#if H1_TEST_FRAMES > 0
            if (total_frames >= H1_TEST_FRAMES) input.exit_requested = 1;
#endif
            if (trace) h1_diag("FRAME_CLOCK_BEGIN n=%u", total_frames);
            now = h1_timer_read_ms();
            if ((uint32_t)(h1_raw_tick_80hz()-heartbeat_tick)>=2400u) {
                /* File commit can exceed the PCM prefill duration on H1. */
                remember_heartbeat(now);
                heartbeat_tick=h1_raw_tick_80hz();
            }
            if (trace) h1_diag("FRAME_CLOCK_END n=%u ms=%u", total_frames, now);
            if ((save_enabled && (uint32_t)(now-saved_at)>=10000u) ||
                (rtc_enabled && (uint32_t)(h1_raw_tick_80hz()-rtc_saved_at)>=4800u)) {
                h1_profile_push(HP_SAVE);
                int checkpoint;
                if (core->save_sync) core->save_sync();
                checkpoint = save_enabled ? save_checkpoint(&store, save, save_size) : 0;
                if (rtc_enabled && (uint32_t)(h1_raw_tick_80hz()-rtc_saved_at)>=4800u) {
                    if (save_checkpoint(&rtc_store,rtc_save,rtc_size)<0) checkpoint=-1;
                    rtc_saved_at=h1_raw_tick_80hz();
                }
                if (checkpoint || h1_diag_is_verbose()) h1_diag("SAVE_CHECKPOINT_END status=%d",checkpoint);
                if (checkpoint < 0) {
                    log_line("SAVE checkpoint failed");
                    h1_message_box(0, "Save write failed. Check storage. Exit will retry.", "H1 GBA", 0);
                    clear_input(0);
                }
                saved_at = h1_timer_read_ms();
                h1_profile_pop();
            }
            /* 59.7275 Hz logic; discard accumulated lag on a slow H1. */
            if ((uint32_t)(now - start) > 1000u) { start = now; frames = 0; }
            if (trace) h1_diag("FRAME_WAIT_BEGIN n=%u", total_frames);
            profile_waiting=1;h1_profile_push(HP_WAIT);
            if (H1_BENCHMARK) {
                /* Bounded comparisons measure the core without waiting. */
            } else if (gba_audio_pacing()) {
                /* PCM playback is the clock: H1's software millisecond timer
                 * loses ticks under audio IRQ load and would starve the mixer. */
                while (gba_audio_wait() && !input.exit_requested && !input.menu_requested && !input.pause_requested) poll();
            } else {
                while ((uint32_t)(h1_timer_read_ms() - start) < frames * 16743u / 1000u &&
                       !input.exit_requested && !input.menu_requested && !input.pause_requested) poll();
            }
            h1_profile_pop();profile_waiting=0;h1_profile_pop();
            h1_profile_frame(profile_core,videos-profile_videos);
            if (trace) h1_diag("FRAME_WAIT_END n=%u", total_frames);
        }
        h1_diag("TIMER_STOP_BEGIN"); h1_timer_stop(); h1_diag("TIMER_STOP_END");
        gba_audio_close();h1_profile_dump("exit");
        dump_heartbeats();
        h1_config_save(&config,&input);
        snprintf(line, sizeof(line), "STOP video=%u errors=%u", videos, video_errors); log_line(line);
        h1_diag("SAVE_EXIT_BEGIN enabled=%d", save_enabled);
        if (core->save_sync) core->save_sync();
        pick = save_enabled ? save_checkpoint(&store, save, save_size) : 0;
        if (rtc_enabled && save_checkpoint(&rtc_store, rtc_save, rtc_size) < 0) pick = -1;
        h1_diag("SAVE_EXIT_END status=%d", pick);
        if (pick < 0) {
            h1_message_box(0, "Save failed; the previous verified slot is retained.", "H1 GBA", 0); result = 3;
        }
        h1_diag("CORE_UNLOAD_BEGIN"); core->unload(); h1_diag("CORE_UNLOAD_END");
        h1_diag("CORE_DEINIT_BEGIN"); core->deinit(); h1_diag("CORE_DEINIT_END");
        gba_gui_close();
        if (input.exit_requested) break;
        clear_input(1);
    }
    free(screen); screen = 0;
    h1_diag("APP_END result=%d", result);
    return result;
}
