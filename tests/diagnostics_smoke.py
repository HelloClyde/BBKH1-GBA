"""Verify durable diagnostic records with blocked mocked H1 services."""
import argparse
import json
from pathlib import Path
from mips_smoke import Machine, ROOT

LOG_PATH = 'A:\\GBA\\h1gba.log'


class BlockedService(Machine):
    def __init__(self, bda, stage):
        self.stage, self.blocked = stage, False
        super().__init__(bda, menu=True)

    def stop(self):
        self.blocked = True
        self.uc.emu_stop()
        return 0

    def alloc(self, n, *args):
        if self.stage == 'allocation' and n >= 1024 * 1024:
            return self.stop()
        return super().alloc(n, *args)

    def fread(self, ptr, size, count, handle, *args):
        if self.stage == 'read' and self.handles[handle][0].endswith('.gba') and b'ROM_READ_BEGIN' in self.files.get(LOG_PATH,b''):
            return self.stop()
        return super().fread(ptr, size, count, handle, *args)

    def game_buffer(self, *args):
        if self.stage == 'video' and self.blits >= 1:
            return self.stop()
        return super().game_buffer(*args)


class LogUpdateFailure(Machine):
    def fopen(self, path, mode, *args):
        if self.string(path) == LOG_PATH and self.string(mode) in ('r+b', 'rb+'):
            if len(self.files.get(LOG_PATH, b'')) > 256:
                return 0
        return super().fopen(path, mode, *args)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bda', type=Path, default=ROOT / 'build/release-debug/H1GBA.bda')
    args = parser.parse_args()
    records = {}
    for stage, marker in [('allocation', 'ALLOC_BEGIN'), ('read', 'ROM_READ_BEGIN'),
                          ('video', 'VIDEO_SCALE_BEGIN')]:
        machine = BlockedService(args.bda, stage)
        machine.uc.emu_start(0x83c00020, 0, timeout=10_000_000, count=100_000_000)
        assert machine.blocked and not machine.finished, stage
        # Mock storage commits writes only at fclose, just like the runtime's contract.
        log = machine.files[LOG_PATH].decode('gbk')
        last = log.splitlines()[-1]
        assert marker in last, (stage, last)
        assert not any(path == LOG_PATH for path, _, _ in machine.handles.values())
        records[stage] = last
    failure = LogUpdateFailure(args.bda, menu=True)
    failure.run()
    retained = failure.files[LOG_PATH].decode('gbk')
    assert 'APP_BEGIN' in retained and 'APP_END' not in retained
    assert failure.blits >= 10  # Logging failure does not prevent game execution.
    good = Machine(args.bda, menu=True)
    good.run()
    out = ROOT / 'build/verification'
    out.mkdir(parents=True, exist_ok=True)
    (out / 'h1gba-example.log').write_bytes(good.files[LOG_PATH])
    report = {'ok': True, 'kind': 'MIPS BDA with blocked mocked firmware services',
              'last_closed_record': records, 'update_open_failure_preserves_log': True}
    (out / 'diagnostics-smoke.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
