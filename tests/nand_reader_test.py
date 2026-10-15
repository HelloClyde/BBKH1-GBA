"""Check sparse H1 NAND commit tails and rejection of incomplete writes."""
import struct,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from read_h1_test_file import H1Nand,PAGE,STRIDE,PAGES

with tempfile.TemporaryDirectory() as directory:
    path=Path(directory)/'synthetic.raw'
    data=bytearray(b'\xff'*(66*PAGES*STRIDE))
    def oob(physical,page,marker,last,sequence,logical):
        start=(physical*PAGES+page)*STRIDE+PAGE
        spare=bytearray(b'\xff'*64);spare[1]=marker
        struct.pack_into('<H',spare,2,last)
        struct.pack_into('<HI',spare,58,sequence,0xffff0000|logical)
        data[start:start+64]=spare
    def check(expected,torn):
        path.write_bytes(data);nand=H1Nand(path)
        try:
            assert nand.mapping==expected,(nand.mapping,expected)
            assert nand.torn==torn,(nand.torn,torn)
        finally:nand.stream.close()
    oob(64,0,0,127,1,7);oob(64,127,0,127,1,7)
    check({7:(64,1)},0)
    # Page zero is unused in a sparse newer unit; its committed tail must
    # still match. Do not fall back to the older copy just for marker 0xff.
    oob(65,0,255,114,2,7);oob(65,114,0,114,2,7)
    check({7:(65,2)},0)
    # Missing tail commit, wrong sequence, wrong logical unit and bad page
    # indexes all keep the prior valid mapping instead of accepting data.
    oob(65,114,255,114,2,7);check({7:(64,1)},1)
    oob(65,114,0,114,3,7);check({7:(64,1)},1)
    oob(65,114,0,114,2,8);check({7:(64,1)},1)
    oob(65,0,255,128,2,7);check({7:(64,1)},1)
print('PASS H1 NAND complete/sparse commits and incomplete-tail rejection')
