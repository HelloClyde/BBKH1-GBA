"""Reproduce H1-only changes in a build copy; keep the pinned submodule clean."""
from pathlib import Path
import shutil


def prepare(source: Path, output: Path, jit=True):
    shutil.copytree(source, output, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns('.git', '*.o', '*.so'))

    def replace(name, old, new):
        path = output / name
        text = path.read_text(encoding='utf-8')
        if text.count(old) != 1:
            raise RuntimeError(f'Pinned gpSP patch context changed: {name}')
        path.write_text(text.replace(old, new), encoding='utf-8')

    replace('sound.h', '#define GBA_SOUND_FREQUENCY   (64 * 1024)',
            '#define GBA_SOUND_FREQUENCY   (32 * 1024)')
    replace('gba_memory.c', 'static bool rtc_enabled = false, rumble_enabled = false;',
            '#include "platform/gba_rtc.h"\n'
            'static bool rtc_enabled = false, rumble_enabled = false;\n'
            'int h1_gba_rtc_enabled(void) { return rtc_enabled; }')
    replace('gba_memory.c', '  rtc_base_time = (s64)t;',
            '  rtc_base_time = (s64)t;\n  h1_gba_rtc_begin();')
    replace('gba_memory.c',
            '  return (time_t)(rtc_base_time +\n'
            '                  (s64)((double)frame_counter * GBA_FRAME_SECONDS));',
            '  return (time_t)h1_gba_rtc_now();')
    replace('gba_memory.c', '        switch (rtc_command) {',
            '        if ((rtc_command & 0xf0) != 0x60) {\n'
            '          u32 reverse = 0;\n'
            '          for (unsigned i = 0; i < 8; ++i) reverse |= ((rtc_command >> i) & 1) << (7-i);\n'
            '          rtc_command = reverse;\n        }\n'
            '        switch (rtc_command) {')
    replace('gba_memory.c', '        case RTC_COMMAND_RESET:\n        case RTC_COMMAND_WRITE_STATUS:',
            '        case RTC_COMMAND_RESET:\n'
            '          rtc_status = 0; rtc_state = RTC_IDLE; break;\n'
            '        case 0x64:\n        case 0x66:\n'
            '          rtc_state = RTC_INPUT_DATA; rtc_data = 0;\n'
            '          rtc_data_bits = rtc_command == 0x64 ? 56 : 24;\n'
            '          rtc_write_mode = rtc_command == 0x64 ? RTC_WRITE_TIME_FULL : RTC_WRITE_TIME;\n'
            '          break;\n        case RTC_COMMAND_WRITE_STATUS:')
    replace('gba_memory.c', 'encode_bcd(current_time->tm_year)',
            'encode_bcd(current_time->tm_year % 100)')
    path = output / 'gba_memory.c'
    text = path.read_text(encoding='utf-8')
    text = text.replace('encode_bcd(current_time->tm_hour)',
        'encode_bcd((rtc_status & 0x40) ? current_time->tm_hour : current_time->tm_hour % 12) | '
        '((!(rtc_status & 0x40) && current_time->tm_hour >= 12) ? 0x80 : 0)')
    # Parenthesize the hour before the u64 cast/shift in full date output.
    text = text.replace('((u64)encode_bcd((rtc_status', '((u64)(encode_bcd((rtc_status')
    text = text.replace('? 0x80 : 0) << 32)', '? 0x80 : 0)) << 32)')
    text = text.replace('rtc_data = (encode_bcd((rtc_status', 'rtc_data = (encode_bcd((rtc_status')
    path.write_text(text, encoding='utf-8')
    replace('gba_memory.c', '      rtc_data <<= 1;\n      rtc_data |= ((new >> 1) & 1);',
            '      rtc_data |= (u64)((new >> 1) & 1) << rtc_bit_count++;')
    replace('gba_memory.c', '        rtc_status = rtc_data; // HACK: assuming write status here.',
            '        if (rtc_write_mode == RTC_WRITE_STATUS) rtc_status = rtc_data & 0x6a;\n'
            '        else h1_gba_rtc_set(rtc_data, rtc_write_mode == RTC_WRITE_TIME_FULL, rtc_status);')
    # Optional profiler wrappers include all early returns, and compile away
    # completely in normal builds. Nested scopes charge time exclusively.
    def profile_wrapper(name, declaration, symbol, kind):
        path = output / name
        text = path.read_text(encoding='utf-8')
        renamed = declaration.replace(symbol, 'h1_profile_original_' + symbol)
        if text.count(declaration) != 1:
            raise RuntimeError(f'Profile context changed: {name}: {symbol}')
        text = text.replace(declaration, '#if H1_PROFILE\n' + renamed + '\n#else\n' + declaration + '\n#endif')
        start = text.index(renamed)
        brace = text.index('{', start)
        depth, end = 1, brace + 1
        while depth:
            depth += (text[end] == '{') - (text[end] == '}')
            end += 1
        wrapper = ('\n#if H1_PROFILE\n' + declaration + '\n{ h1_profile_push(' + kind + '); '
            + 'h1_profile_original_' + symbol + '(); h1_profile_pop(); }\n#endif\n')
        text = '#include "platform/profile.h"\n' + text[:end] + wrapper + text[end:]
        path.write_text(text, encoding='utf-8')
    profile_wrapper('video.cc', 'void update_scanline(void)', 'update_scanline', 'HP_RENDER')
    profile_wrapper('sound.c', 'void render_gbc_sound()', 'render_gbc_sound', 'HP_MIX')
    profile_wrapper('libretro/libretro.c', 'static void audio_run(void)', 'audio_run', 'HP_MIX')
    if not jit:
        return output
    replace('cpu_threaded.c',
            '    __builtin___clear_cache(baseaddr, endptr);',
            '    extern void h1_jit_cache_sync(void *, void *);\n'
            '    h1_jit_cache_sync(baseaddr, endptr);')
    replace('libretro/libretro.c',
            '   ram_translation_cache = &rom_translation_cache[ROM_TRANSLATION_CACHE_SIZE];',
            '   ram_translation_cache = rom_translation_cache ?\n'
            '      &rom_translation_cache[ROM_TRANSLATION_CACHE_SIZE] : NULL;')
    replace('main.c', '  init_dynarec_caches();\n  init_emitter(gamepak_must_swap());',
            '  if (rom_translation_cache) {\n'
            '    init_dynarec_caches();\n    init_emitter(gamepak_must_swap());\n  }')
    replace('mips/mips_stub.S', '  .set mips32r2', '  .set mips32')
    # H1 firmware restores its own GP on a hardware interrupt. Upstream caches
    # GBA r13 in GP, corrupting the GBA stack in real firmware (mock ABI alone
    # does not show this). Use s3 for r13 and materialize guest PC literals.
    replace('mips/mips_emit.h', '#define reg_r13     mips_reg_gp',
            '#define reg_r13     mips_reg_s3')
    path = output / 'mips/mips_emit.h'
    text = path.read_text(encoding='utf-8')
    begin = text.index('#define generate_load_pc(')
    end = text.index('#define generate_store_reg(', begin)
    text = text[:begin] + ('#define generate_load_pc(ireg, new_pc) \\\n'
                           '  generate_load_imm(ireg, (new_pc))\n\n') + text[end:]
    text = text.replace('  generate_load_imm(reg_pc, stored_pc)', '  /* H1 keeps GBA SP in s3; PC is emitted as a literal. */')
    path.write_text(text, encoding='utf-8')
    replace('mips/mips_stub.S', '  sw $28, REG_R13($16)', '  sw $19, REG_R13($16)')
    replace('mips/mips_stub.S', '  lw $28, REG_R13($16)', '  lw $19, REG_R13($16)')
    # The upstream R1 patcher has no cache sync or explicit JR delay slot.
    # Jump to a tiny H1 trampoline. It preserves all live JIT registers and
    # keeps every generated patch handler inside its fixed 64-byte slot.
    replace('mips/mips_emit.h', '  #if defined(PSP)\n    mips_emit_cache(0x1A, mips_reg_ra, -8);',
            '  #if defined(H1_JIT)\n'
            '    extern void h1_jit_patch_sync(void);\n'
            '    mips_emit_j(((u32)&h1_jit_patch_sync) >> 2);\n'
            '    mips_emit_nop();\n'
            '  #elif defined(PSP)\n    mips_emit_cache(0x1A, mips_reg_ra, -8);')
    replace('mips/mips_emit.h', '  // Round up handlers to 16 instructions for easy addressing',
            '  if (translation_ptr - *tr_ptr > 64) __builtin_trap();\n'
            '  // Round up handlers to 16 instructions for easy addressing')
    return output
