"""Execute MIPS audio against delayed and stalled PCM consumers."""
import json
import struct
from mips_smoke import Machine, ROOT
from make_test_rom import make_rom


class Stalled(Machine):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.audio_consumes = False
        self.retained = None

    def pcm_submit(self, route, descriptor, repeats, flags, *a):
        if not descriptor:
            if self.retained:
                pcm, data = self.retained
                assert self.read(pcm, len(data)) == data, 'Overwrote unread PCM'
            self.retained = None
            return super().pcm_submit(route, descriptor, repeats, flags, *a)
        pcm, size = struct.unpack('<2I', self.read(descriptor, 8))
        self.retained = (pcm, self.read(pcm, 2048 * 2))
        return super().pcm_submit(route, descriptor, repeats, flags, *a)


def main():
    path = 'A:\\GBA\\AUDIO.gba'
    bda = ROOT / 'build/release/H1GBA.bda'
    results = {}
    for name, cls in [('delayed', Machine), ('stalled', Stalled)]:
        machine = cls(bda, files={path: make_rom(tone=True)}, path=path, menu=True)
        machine.run()
        pcm = b''.join(machine.audio_observed)
        values = struct.unpack('<' + 'h' * (len(pcm) // 2), pcm)
        assert max(values) > 1000 and min(values) < -1000
        assert 'AUDIO_OPEN_END ready=1' in machine.files['A:\\GBA\\h1gba.log'].decode()
        results[name] = {'blocks': len(machine.audio_submissions), 'min': min(values), 'max': max(values)}
        if name == 'stalled':
            assert len(machine.audio_submissions) == 1
            assert not machine.retained
            log = machine.files['A:\\GBA\\h1gba.log'].decode()
            import re
            assert 'AUDIO_STALL disabling_output=1' in log
    out = ROOT / 'build/verification/audio-smoke.json'
    out.write_text(json.dumps({'ok': True, 'kind': 'MIPS with mocked PCM services', **results}, indent=2))
    print(out.read_text())


if __name__ == '__main__':
    main()
