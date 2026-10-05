"""Patch the local QEMU overlay: unrelated TCU writes must not defer matches.

Use before rebuilding the private test emulator. Does not modify firmware,
NAND dumps, or the BDA. Preserve the original source in the evidence directory.
"""
import argparse,hashlib,json
from pathlib import Path

def patch(s):
    changes=[('''        int64_t full = tcu_next_deadline_ns(s, ch, false, now_ns);
        int64_t half = tcu_next_deadline_ns(s, ch, true, now_ns);''','''        /* Keep a match deadline across writes to unrelated channels. Re-
         * calculating from the rounded counter loses its fractional phase;
         * frequent TFCR writes can defer or skip a FULL match entirely. */
        uint32_t bit = 1u << ch;
        int64_t full = !tcu_counter_running(s, ch) || (s->pending_mask & bit) ? 0 :
            s->deadline_ns[ch] ? s->deadline_ns[ch] :
            tcu_next_deadline_ns(s, ch, false, now_ns);
        int64_t half = !tcu_counter_running(s, ch) || (s->pending_mask & (bit << TCU_HALF_SHIFT)) ? 0 :
            s->half_deadline_ns[ch] ? s->half_deadline_ns[ch] :
            tcu_next_deadline_ns(s, ch, true, now_ns);'''),
        ('''    case TCU_TFCR:
        s->pending_mask &= ~(value & TCU_FLAG_MASK);''','''    case TCU_TFCR:
        for (unsigned ch = 0; ch < JZ4740_TCU_CHANNELS; ch++) {
            if (value & (1u << ch)) s->deadline_ns[ch] = 0;
            if (value & ((1u << ch) << TCU_HALF_SHIFT)) s->half_deadline_ns[ch] = 0;
        }
        s->pending_mask &= ~(value & TCU_FLAG_MASK);'''),
        ('''    s->counter[channel] = value;
    s->counter_anchor_ns[channel]''','''    s->deadline_ns[channel] = s->half_deadline_ns[channel] = 0;
    s->counter[channel] = value;
    s->counter_anchor_ns[channel]'''),
        ('''        } else if (reg == TCU_TCSR) {
            tcu_latch_counter(s, channel, now_ns);''','''        } else if (reg == TCU_TCSR) {
            s->deadline_ns[channel] = s->half_deadline_ns[channel] = 0;
            tcu_latch_counter(s, channel, now_ns);'''),
        ('''    } else {
        s->compare[channel] = compare;
        if (compare != 0''','''    } else {
        s->half_deadline_ns[channel] = 0;
        s->compare[channel] = compare;
        if (compare != 0''')]
    for before,after in changes:
        if after in s: continue
        if s.count(before)!=1: raise ValueError('Unexpected overlay source: '+before[:70])
        s=s.replace(before,after,1)
    return s

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('source',type=Path)
    p.add_argument('--evidence',type=Path,required=True)
    a=p.parse_args();original=a.source.read_bytes();updated=patch(original.decode()).encode()
    a.evidence.mkdir(parents=True,exist_ok=True)
    backup=a.evidence/'jz4740_tcu-original.c'
    if not backup.exists(): backup.write_bytes(original)
    a.source.write_bytes(updated)
    (a.evidence/'tcu-deadline-patch.json').write_text(json.dumps({
        'source':str(a.source),'original_sha256':hashlib.sha256(backup.read_bytes()).hexdigest(),
        'patched_sha256':hashlib.sha256(updated).hexdigest()},indent=2)+'\n')
    print('Patched TCU deadline preservation:',a.source)
if __name__=='__main__':main()
