"""Execute actual emitted MIPS code, RAM self-modification and low-memory fallback."""
import json
import re
import struct
from unicorn import UC_HOOK_BLOCK
from unicorn.mips_const import UC_MIPS_REG_GP
from mips_smoke import Machine, ROOT
from make_test_rom import make_rom


def selfmod_rom():
    original = make_rom(tone=True)
    rom = bytearray(original)
    rom[0x400:0x740] = original[0xc0:0x400]
    words, literals = [], []

    def ldr(register, value):
        literals.append((len(words), register, value))
        words.append(0)

    ldr(6, 0x0e000000)
    ldr(13, 0x03007e00)
    # Rewrite an already compiled Thumb function, then an ARM function.
    for base, instruction, result, slot in [
        (0x03001001, 0xb5012011, 0x11, 1),
        (0x03001001, 0xb5012022, 0x22, 2),
        (0x03002000, 0xe3a00033, 0x33, 3),
        (0x03002000, 0xe3a00044, 0x44, 4),
    ]:
        ldr(5, base & ~1)
        ldr(1, instruction)
        words.append(0xe5851000)  # str r1,[r5]
        tail = [0x468ebc03, 0x46c04770] if base & 1 else [0xe92d4001, 0xe8bd4001, 0xe12fff1e]
        for offset, instruction in enumerate(tail, 1):
            ldr(1, instruction)
            words.append(0xe5851000 | (offset * 4))
        ldr(4, base)
        words += [0xe28fe000, 0xe12fff14]  # add lr,pc,#0; bx r4
        words.append(0xe5c60000 | slot)  # strb returned r0,[r6,#slot]
    pc = 0xc0 + len(words) * 4
    words.append(0xea000000 | ((0x400 - pc - 8) // 4 & 0xffffff))
    for index, register, value in literals:
        offset = len(words) * 4 - index * 4 - 8
        words[index] = 0xe59f0000 | register << 12 | offset
        words.append(value)
    payload = struct.pack('<%dI' % len(words), *words)
    assert len(payload) < 0x340
    rom[0xc0:0xc0 + len(payload)] = payload
    return bytes(rom)


class LowMemory(Machine):
    def alloc(self, n, *args):
        if 2_400_000 < n < 2_600_000:
            return 0
        return super().alloc(n, *args)


def main():
    bda = ROOT / 'build/test-20/H1GBA.bda'
    path = 'A:\\GBA\\SELFTEST.gba'
    results = {}
    for name, cls in [('jit', Machine), ('low_memory', LowMemory)]:
        machine = cls(bda, files={path: selfmod_rom()}, path=path)
        executed = [0]
        def compiled_block(uc, addr, size, data):
            executed[0] += 1
            # H1 interrupts put back the firmware GP; it cannot cache GBA SP.
            if executed[0] % 97 == 0:
                uc.reg_write(UC_MIPS_REG_GP, 0x80582d58)
        machine.uc.hook_add(UC_HOOK_BLOCK, compiled_block,
                            begin=0x81000000, end=0x83800000)
        seconds = machine.run()
        machine.check_frame(False)
        slot = machine.files[path + '.s0']
        assert slot[28:33] == bytes([0x5a, 0x11, 0x22, 0x33, 0x44]), slot[28:33].hex()
        log = machine.files['A:\\GBA\\h1gba.log'].decode('gbk')
        if name == 'jit':
            assert 'JIT_STATE enabled=1' in log
            assert executed[0] > 1000, executed
            assert re.search(r'JIT_FREE_BEGIN .*sync_calls=[1-9]', log)
            assert 'JIT_FREE_END' in log
        else:
            assert 'JIT_STATE enabled=0' in log
            assert 'JIT_ALLOC_END ready=0' in log
            assert executed[0] == 0
        results[name] = {'seconds': round(seconds, 3), 'emitted_blocks_executed': executed[0],
                         'ARM_and_Thumb_self_modification': True, 'stack_survives_firmware_GP': True,
                         'save_first_5_bytes': slot[28:33].hex()}
    report = {'ok': True, 'kind': 'actual MIPS JIT in Unicorn with mocked H1 services', **results}
    output = ROOT / 'build/verification/jit-smoke.json'
    output.write_text(json.dumps(report, indent=2) + '\n')
    print(output.read_text())


if __name__ == '__main__':
    main()
