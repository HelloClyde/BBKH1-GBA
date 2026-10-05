"""Check the physical-style calibration test, plus the old rejection predicate."""
from pathlib import Path
import os,shutil,subprocess
root=Path(__file__).resolve().parents[1]
out=root/'build/profile-unit';legacy=out/'legacy-boundary';legacy.mkdir(parents=True,exist_ok=True)
gcc=os.environ.get('HOST_CC') or shutil.which('gcc')
if not gcc:raise SystemExit('HOST_CC or gcc is required')
def compile_run(source,exe):
    subprocess.run([gcc,'-std=c11','-O2','-Wall','-Wextra','-I',str(out),str(source),'-o',str(exe)],check=True)
    return subprocess.run([str(exe)],capture_output=True,text=True)
good=compile_run(root/'tests/profile_physical_boundary.c',out/'physical-boundary.exe')
assert good.returncode==0,good.stderr
print(good.stdout.strip())
for name in ('profile.c','profile.h','diagnostics.h'):
    shutil.copyfile(root/'src/platform'/name,legacy/name)
header=(root/'src/platform/profile_clock.h').read_text()
predicate='a<=PC_TOP && b<=PC_TOP'
assert header.count(predicate)==1
(legacy/'profile_clock.h').write_text(header.replace(predicate,'a<PC_TOP && b<PC_TOP'))
harness=(root/'tests/profile_physical_boundary.c').read_text()
(out/'legacy-boundary-test.c').write_text(harness.replace('../src/platform/profile.c','legacy-boundary/profile.c'))
bad=compile_run(out/'legacy-boundary-test.c',out/'legacy-boundary-test.exe')
assert bad.returncode!=0,'The old invalid-terminal predicate should fail calibration'
print('PASS negative control: old 65535 rejection fails this calibration test')
