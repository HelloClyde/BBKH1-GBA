"""Context-checked cartridge RAM fixes; leave the pinned upstream clean."""
from pathlib import Path

def prepare(core: Path, output: Path):
    text = (core / 'mem.c').read_text(encoding='utf-8')
    def patch(old, new, count=1):
        nonlocal text
        if text.count(old) != count: raise RuntimeError('gnuboy patch context changed: '+old)
        text = text.replace(old,new)
    patch('struct mbc mbc;', 'extern unsigned h1_gb_ram_bytes;\nstruct mbc mbc;')
    # Small RAM and MBC2 need address mirroring / nibble reads, so bypass the
    # direct 8 KiB maps. Timer-selected MBC3 accesses already bypass them.
    patch('if (mbc.enableram && !(rtc.sel&8))',
          'if (mbc.enableram && !(rtc.sel&8) && mbc.type != MBC_MBC2 && h1_gb_ram_bytes >= 8192)', 2)
    patch('ram.sbank[mbc.rambank][a & 0x1FFF] = b;',
          'if (!h1_gb_ram_bytes) break;\n\t\tif (mbc.type == MBC_MBC2) b &= 15;\n\t\tram.sbank[mbc.rambank][a & (h1_gb_ram_bytes < 8192 ? h1_gb_ram_bytes - 1 : 8191)] = b;')
    patch('return ram.sbank[mbc.rambank][a & 0x1FFF];',
          'if (!h1_gb_ram_bytes) return 0xff;\n\t\treturn ram.sbank[mbc.rambank][a & (h1_gb_ram_bytes < 8192 ? h1_gb_ram_bytes - 1 : 8191)] | (mbc.type == MBC_MBC2 ? 0xf0 : 0);')
    patch('mbc.rombank = b & 0x0F;', 'mbc.rombank = (b & 0x0F) ? b & 0x0F : 1;')
    output.mkdir(parents=True,exist_ok=True)
    target=output/'mem.c'; target.write_text(text,encoding='utf-8')
    return target
