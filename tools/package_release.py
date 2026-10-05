"""Package explicit release files and full pinned dependency source (no ROM/dump)."""
import argparse,hashlib,json,subprocess,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def tracked(repo):
    data=subprocess.check_output(['git','-C',str(repo),'ls-files','--stage','-z'])
    for entry in data.split(b'\0'):
        if not entry:continue
        modepath=entry.decode('utf-8').split('\t',1)
        if not modepath[0].startswith('160000 '):yield modepath[1]

def add(zipper,name,data):
    info=zipfile.ZipInfo(name,(2026,10,6,0,0,0))
    info.compress_type=zipfile.ZIP_DEFLATED
    info.external_attr=0o100644<<16
    zipper.writestr(info,data)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version',default='v0.12.3')
    args=parser.parse_args()
    if args.version!='v0.12.3':parser.error('Update release metadata and runtime evidence before a new version')
    output=ROOT/'dist/release';output.mkdir(parents=True,exist_ok=True)
    files=[]
    for name in ['H1GBA.bda','H1GBA-profile.bda','H1GBA.build.json','H1GBA-profile.build.json']:
        import shutil
        shutil.copyfile(ROOT/'dist'/name,output/name);files.append(name)
    install=f'BBKH1-GBA-{args.version}-install.zip'
    with zipfile.ZipFile(output/install,'w') as archive:
        add(archive,'应用/程序/GameBoy.bda',(ROOT/'dist/H1GBA.bda').read_bytes())
        add(archive,'GBA/',b'')
        for name in ['README.md','LICENSE','NOTICE.md']:
            add(archive,name,(ROOT/name).read_bytes())
        for path in sorted((ROOT/'assets/licenses').glob('*')):
            add(archive,'licenses/'+path.name,path.read_bytes())
    files.append(install)
    source=f'BBKH1-GBA-{args.version}-source.zip'
    with zipfile.ZipFile(output/source,'w') as archive:
        prefix=f'BBKH1-GBA-{args.version}/'
        repos=[(ROOT,''),(ROOT/'vendor/h1-sdk','vendor/h1-sdk/'),(ROOT/'third_party/gpsp','third_party/gpsp/'),(ROOT/'third_party/gnuboy','third_party/gnuboy/')]
        for repo,rel in repos:
            for name in sorted(tracked(repo)):
                path=repo/name
                if path.is_file():add(archive,prefix+rel+name,path.read_bytes())
        revision={'application':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),**{rel.rstrip('/'):subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip() for repo,rel in repos[1:]}}
        add(archive,prefix+'SOURCE-REVISION.json',json.dumps(revision,indent=2).encode())
    files.append(source)
    manifest=''.join(hashlib.sha256((output/name).read_bytes()).hexdigest()+'  '+name+'\n' for name in sorted(files))
    (output/'SHA256SUMS.txt').write_text(manifest,encoding='ascii')
    print(manifest)

if __name__=='__main__':main()
