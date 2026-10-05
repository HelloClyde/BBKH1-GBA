"""Verify GameBoy titles, icon resources, metadata and optional payload baseline."""
import argparse,hashlib,importlib.util,json,re,struct,sys
from pathlib import Path
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'vendor/h1-sdk'))
from h1_bda.resources import RESOURCE_OFFSET,PAYLOAD_OFFSET,RESOURCE_SPECS,RESOURCE_SIZES,build_icon_resources
from h1_bda.validate import validate_bda
from h1_bda.header import decode_header,read_c_string,TITLE_OFFSET,TITLE_SIZE
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native',action='store_true',help='Check stopped private H1 firmware test and screenshots')
    parser.add_argument('--baseline',type=Path,help='Optional directory for executable equality check')
    args=parser.parse_args()
    icon=ROOT/'assets/gba-icon.png';region=build_icon_resources(icon)
    work=ROOT/'build/icon-design';work.mkdir(exist_ok=True)
    spec=importlib.util.spec_from_file_location('h1_icon_extract',ROOT/'vendor/h1-sdk/scripts/extract_bda_icons.py')
    extract=importlib.util.module_from_spec(spec);spec.loader.exec_module(extract)
    # The display title H1 GB/GBA contains a slash; sanitize extraction filenames
    # without changing the BDA title or the pinned SDK checkout.
    read_title=extract.read_c_string
    extract.read_c_string=lambda data:read_title(data).replace('/','-').replace('\\','-')
    packages=[]
    names=[name for name in ['H1GBA','H1GBA-interpreter','H1GBA-debug'] if (ROOT/'dist'/(name+'.bda')).is_file()]
    assert 'H1GBA' in names,'Build the normal release first'
    if not args.baseline and (ROOT/'dist/H1GBA-profile.bda').exists(): names.append('H1GBA-profile')
    for name in names:
        path=ROOT/'dist'/(name+'.bda');data=path.read_bytes()
        original=(args.baseline/path.name).read_bytes() if args.baseline else None
        assert validate_bda(path)['ok']
        assert data[RESOURCE_OFFSET:PAYLOAD_OFFSET]==region
        assert read_c_string(decode_header(data)[TITLE_OFFSET:TITLE_OFFSET+TITLE_SIZE])=='GameBoy'
        if original is not None:
            assert data[PAYLOAD_OFFSET:]==original[PAYLOAD_OFFSET:], 'Executable differs from selected baseline'
        metadata=json.loads(path.with_suffix('.build.json').read_text())
        digest=hashlib.sha256(data).hexdigest()
        assert metadata['sha256']==digest and metadata['icon_sha256']==hashlib.sha256(icon.read_bytes()).hexdigest()
        assert path.with_suffix('.bda.sha256').read_text().split()==[digest,path.name]
        packages.append({'file':path.name,'sha256':digest,'bytes':len(data),'payload_unchanged': original is not None})
    paths=extract.extract_icons(ROOT/'dist/H1GBA.bda',work/'extracted')
    offset=0;resources=[]
    preview=Image.new('RGB',(680,238),(34,39,47));draw=ImageDraw.Draw(preview)
    for i,((w,h,bits),size,path) in enumerate(zip(RESOURCE_SPECS,RESOURCE_SIZES,paths)):
        block=region[offset:offset+size]
        assert struct.unpack_from('<6H',block)==(w,h,bits,1,w,h)
        assert not any(block[12+w*h*(bits//8):])
        im=Image.open(path).convert('RGBA');assert im.size==(w,h)
        if bits==24:assert im.getchannel('A').getextrema()==(0,255)
        zoom=im.resize((w*2,h*2),Image.Resampling.NEAREST)
        preview.paste(zoom,(i*170+(170-w*2)//2,18),zoom)
        preview.paste(im,(i*170+(170-w)//2,153),im)
        draw.text((i*170+34,217),f'{w}x{h} / {bits}bit',fill='white')
        resources.append({'index':i,'width':w,'height':h,'bits':bits,'size':size})
        offset+=size
    preview.save(work/'packed-icons-preview.png')
    report={'ok':True,'icon':str(icon),'icon_sha256':hashlib.sha256(icon.read_bytes()).hexdigest(),
        'resources':resources,'packages':packages,'payload_unchanged':args.baseline is not None}
    if args.native:
        sys.path.insert(0,str(ROOT/'tools'))
        from read_h1_test_file import H1Nand,Fat16
        status=json.loads((work/'native-status.json').read_text())
        assert not status['running'] and status['returncode']==0 and not status['last_error']
        image_build=json.loads((ROOT/'build/h1-emulator-test/image-build.json').read_text())
        assert image_build['bda_sha256']==packages[0]['sha256']
        nand=H1Nand(ROOT/'build/h1-emulator-test/h1-system.raw')
        try:
            assert nand.torn==0
            raw=Fat16(nand).file('GBA/h1gba.log');(work/'native-run.log').write_bytes(raw)
        finally:nand.stream.close()
        log=raw.decode('gbk');assert 'APP_END result=0' in log
        assert 'PAUSE_MENU_BEGIN' in log and 'PAUSE_MENU_END action=0' in log
        frames,errors=re.search(r'STOP video=(\d+) errors=(\d+)',log).groups()
        assert int(frames)>50 and errors=='0'
        for name in ('h1-desktop-icon.png','h1-icon-picker.png','h1-icon-pause.png'):
            with Image.open(work/name) as im:assert im.size==(480,272)
        report['native']={'firmware':'H1 V1.41','desktop_screenshot':'build/icon-design/h1-desktop-icon.png',
            'game_video_frames':int(frames),'video_errors':0,'pause_resume':True,'normal_exit':True,'torn_records':0}
    (work/'verification.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
