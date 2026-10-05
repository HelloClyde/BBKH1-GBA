"""Compare guest instructions per retro_run; this is not physical H1 FPS."""
import hashlib
import json
import subprocess
from unicorn import UC_HOOK_BLOCK, UC_HOOK_CODE
from unicorn.mips_const import UC_MIPS_REG_RA
from mips_smoke import Machine, ROOT
from jit_smoke import selfmod_rom


def measure(core):
    directory = ROOT / ('build/test-40-benchmark' if core == 'jit' else 'build/test-40-interpreter-benchmark')
    symbol_text = subprocess.check_output([str(ROOT / '.tools/toolchain/bin/mipsel-none-elf-nm.exe'),
                                           str(directory / 'H1GBA.elf')], text=True)
    address = next(int(line.split()[0], 16) for line in symbol_text.splitlines()
                   if line.split()[-1] == 'retro_run')
    path = 'A:\\GBA\\SELFTEST.gba'
    machine = Machine(directory / 'H1GBA.bda', files={path: selfmod_rom()}, path=path)
    counts, state = [], {'active': False, 'count': 0, 'returns': set()}

    def enter(uc, pc, size, data):
        state['active'], state['count'] = True, 0
        target = uc.reg_read(UC_MIPS_REG_RA)
        if target not in state['returns']:
            state['returns'].add(target)
            uc.hook_add(UC_HOOK_CODE, leave, begin=target, end=target)

    def leave(uc, pc, size, data):
        counts.append(state['count'])
        state['active'] = False

    def block(uc, pc, size, data):
        if state['active']:
            state['count'] += size // 4

    machine.uc.hook_add(UC_HOOK_CODE, enter, begin=address, end=address)
    machine.uc.hook_add(UC_HOOK_BLOCK, block)
    seconds = machine.run()
    machine.check_frame(False)
    assert len(counts) == 40, len(counts)
    log = machine.files['A:\\GBA\\h1gba.log'].decode('gbk')
    assert 'APP_END result=0' in log and 'AUDIO_OPEN' not in log
    if core == 'jit':
        assert 'JIT_STATE enabled=1' in log
    return {'instructions_per_frame_after_warmup': sum(counts[10:]) / len(counts[10:]),
            'frame_instructions': counts, 'wall_seconds_with_hooks': round(seconds, 3),
            'screen_sha256': hashlib.sha256(machine.screen).hexdigest(),
            'save_sha256': hashlib.sha256(machine.files[path + '.s0'][28:]).hexdigest(),
            'bda_sha256': hashlib.sha256((directory / 'H1GBA.bda').read_bytes()).hexdigest()}


def main():
    interpreter = measure('interpreter')
    jit = measure('jit')
    for key in ('screen_sha256', 'save_sha256'):
        assert interpreter[key] == jit[key], key
    ratio = interpreter['instructions_per_frame_after_warmup'] / jit['instructions_per_frame_after_warmup']
    assert ratio > 1, ratio
    report = {'ok': True, 'kind': 'Unicorn MIPS block instruction counts, 40 identical homebrew frames',
              'interpreter': interpreter, 'jit': jit, 'instruction_reduction_factor': ratio,
              'physical_H1_FPS_measured': False,
              'caveat': 'Block size accounting and Python hooks are not device cycle timing; commercial ROM performance varies.'}
    output = ROOT / 'build/verification/jit-benchmark.json'
    output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k not in ('interpreter', 'jit')}, indent=2))
    for name, result in [('interpreter', interpreter), ('jit', jit)]:
        print(name, result['instructions_per_frame_after_warmup'])


if __name__ == '__main__':
    main()
