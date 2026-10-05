"""Read a file from the private H1 V1.41 NAND after stopping QEMU."""
import argparse
import json
from pathlib import Path
import struct

PAGE, STRIDE, PAGES = 2048, 2112, 128
UNIT = PAGE * PAGES


class H1Nand:
    def __init__(self, path):
        self.stream = path.open('rb')
        self.mapping = {}
        self.torn = 0
        for physical in range(64, path.stat().st_size // (STRIDE * PAGES)):
            first = self.oob(physical, 0)
            tag = struct.unpack_from('<I', first, 60)[0]
            if first[0] != 255 or tag >> 16 != 65535 or tag == 0xffffffff:
                continue
            last_page, sequence = struct.unpack_from('<H', first, 2)[0], struct.unpack_from('<H', first, 58)[0]
            if first[1] != 0 or last_page >= PAGES:
                self.torn += 1
                continue
            last = self.oob(physical, last_page)
            if last[1] != 0 or last[58:64] != first[58:64]:
                self.torn += 1
                continue
            logical = tag & 65535
            previous = self.mapping.get(logical)
            if previous is None or 0 < ((sequence - previous[1]) & 65535) < 32768:
                self.mapping[logical] = (physical, sequence)

    def oob(self, physical, page):
        self.stream.seek((physical * PAGES + page) * STRIDE + PAGE)
        return self.stream.read(64)

    def read(self, address, length):
        result = bytearray()
        while length:
            logical, within = divmod(address, UNIT)
            page, offset = divmod(within, PAGE)
            count = min(length, PAGE - offset)
            mapping = self.mapping.get(logical)
            if mapping is None:
                result.extend(b'\xff' * count)
            else:
                self.stream.seek((mapping[0] * PAGES + page) * STRIDE + offset)
                result.extend(self.stream.read(count))
            address += count
            length -= count
        return bytes(result)


class Fat16:
    def __init__(self, nand):
        self.nand = nand
        self.base = 32 * 512
        boot = nand.read(self.base, 512)
        if boot[510:512] != b'\x55\xaa' or struct.unpack_from('<H', boot, 11)[0] != 512:
            raise ValueError('Invalid H1 FAT16 boot sector')
        self.cluster_bytes = boot[13] * 512
        reserved, copies, roots, fat_sectors = struct.unpack_from('<H', boot, 14)[0], boot[16], struct.unpack_from('<H', boot, 17)[0], struct.unpack_from('<H', boot, 22)[0]
        self.fat = nand.read(self.base + reserved * 512, fat_sectors * 512)
        root_start = self.base + (reserved + copies * fat_sectors) * 512
        self.root = nand.read(root_start, roots * 32)
        self.data_start = root_start + ((roots * 32 + 511) // 512) * 512

    def chain(self, cluster):
        chunks = []
        visited = set()
        while 2 <= cluster < 0xfff8:
            if cluster in visited or cluster * 2 + 2 > len(self.fat):
                raise ValueError('Invalid FAT chain')
            visited.add(cluster)
            chunks.append(self.nand.read(self.data_start + (cluster - 2) * self.cluster_bytes, self.cluster_bytes))
            cluster = struct.unpack_from('<H', self.fat, cluster * 2)[0]
        return b''.join(chunks)

    def file(self, path):
        directory = self.root
        parts = path.replace('\\', '/').strip('/').split('/')
        for index, part in enumerate(parts):
            found = None
            long_parts, long_checksum = {}, None
            for offset in range(0, len(directory), 32):
                entry = directory[offset:offset + 32]
                if entry[0] == 0:
                    break
                if entry[0] == 0xe5:
                    long_parts = {}
                    continue
                if entry[11] == 0x0f:
                    order = entry[0] & 31
                    if entry[0] & 64:
                        long_parts, long_checksum = {}, entry[13]
                    if entry[13] == long_checksum and order:
                        long_parts[order] = entry[1:11] + entry[14:26] + entry[28:32]
                    else:
                        long_parts = {}
                    continue
                if entry[11] & 0x08:
                    long_parts = {}
                    continue
                name, ext = entry[:8].decode('gbk', errors='replace').rstrip(), entry[8:11].decode('gbk', errors='replace').rstrip()
                name += '.' + ext if ext else ''
                checksum = 0
                for value in entry[:11]:
                    checksum = (((checksum & 1) << 7) + (checksum >> 1) + value) & 255
                long_name = ''
                if long_parts and checksum == long_checksum and set(long_parts) == set(range(1, max(long_parts) + 1)):
                    long_name = b''.join(long_parts[n] for n in sorted(long_parts)).decode('utf-16le').split('\0')[0].rstrip('\uffff')
                long_parts = {}
                if part.casefold() in (name.casefold(), long_name.casefold()):
                    found = entry
                    break
            if found is None:
                raise FileNotFoundError(path)
            cluster = struct.unpack_from('<H', found, 26)[0]
            contents = self.chain(cluster)
            if index == len(parts) - 1:
                return contents[:struct.unpack_from('<I', found, 28)[0]]
            if not found[11] & 0x10:
                raise NotADirectoryError(part)
            directory = contents


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--nand', type=Path, default=Path('build/h1-emulator-test/h1-system.raw'))
    parser.add_argument('--file', default='GBA/h1gba.log', help='Path in the FAT volume (8.3 or VFAT long name)')
    parser.add_argument('--output', type=Path, default=Path('build/h1-emulator-test/evidence/h1gba.log'))
    args = parser.parse_args()
    nand = H1Nand(args.nand)
    try:
        data = Fat16(nand).file(args.file)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(data)
        print(json.dumps({'bytes': len(data), 'mapped_units': len(nand.mapping), 'torn_records': nand.torn, 'output': str(args.output.resolve())}))
    finally:
        nand.stream.close()


if __name__ == '__main__':
    main()
