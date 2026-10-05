"""Publish verified workflow assets once; never replace an existing release."""
import os,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def main():
    tag=os.environ['GITHUB_REF_NAME'];repo=os.environ['GITHUB_REPOSITORY']
    if tag!='v0.12.3':raise RuntimeError('Unexpected release tag')
    existing=subprocess.run(['gh','release','view',tag,'--repo',repo],capture_output=True)
    if existing.returncode==0:raise RuntimeError('Release already exists; inspect it before retrying')
    assets=sorted((ROOT/'dist/release').glob('*'))
    assert len(assets)==7
    subprocess.run(['gh','release','create',tag,*map(str,assets),'--repo',repo,'--verify-tag',
        '--title','GameBoy v0.12.3 · H1 GB/GBC/GBA','--notes-file',str(ROOT/'release/v0.12.3.md')],check=True)

if __name__=='__main__':main()
