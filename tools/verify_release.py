"""Validate exact BDA headers/icons/metadata and optionally recorded runtime hashes."""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'vendor/h1-sdk'))
from h1_bda.validate import validate_bda
from h1_bda.header import decode_header,read_c_string,TITLE_OFFSET,TITLE_SIZE
from h1_bda.resources import build_icon_resources,RESOURCE_OFFSET,PAYLOAD_OFFSET

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--require-verified',action='store_true')
    args=parser.parse_args()
    resources=build_icon_resources(ROOT/'assets/gba-icon.png')
    verified=json.loads((ROOT/'release/verified-builds.json').read_text()) if args.require_verified else None
    for name in ['H1GBA','H1GBA-profile']:
        bda=ROOT/'dist'/f'{name}.bda'
        data=bda.read_bytes();digest=hashlib.sha256(data).hexdigest()
        report=validate_bda(bda)
        if not report['ok']:raise RuntimeError(report)
        assert read_c_string(decode_header(data)[TITLE_OFFSET:TITLE_OFFSET+TITLE_SIZE])=='GameBoy'
        assert data[RESOURCE_OFFSET:PAYLOAD_OFFSET]==resources
        meta=json.loads(bda.with_suffix('.build.json').read_text())
        assert meta['sha256']==digest and meta['size']==len(data)
        assert meta['profile']==name.endswith('-profile')
        assert meta['version'].startswith('0.12.3-')
        assert bda.with_suffix('.bda.sha256').read_text().split()[0]==digest
        if verified:assert verified['binaries'][name+'.bda']['sha256']==digest,'BDA differs from runtime-tested release'
        print('PASS',bda.name,len(data),digest)

if __name__=='__main__':main()
