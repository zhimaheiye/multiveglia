"""Build Windows x64 portable package from clean source and pinned dependencies."""
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.request
import zipfile

ROOT=Path(__file__).resolve().parents[1]
VERSION='0.7.1'
PYTHON='3.14.10'
PYTHON_SHA256='90905e64a840557d8c1bc4f5b74db3d7ee85e3ffb217611cac1c7813acea4159'


def main():
    output=ROOT/'dist';output.mkdir(exist_ok=True)
    stage=output/'windows-x64'
    if stage.resolve().parent != output.resolve() or stage.is_symlink():
        raise RuntimeError('Unsafe staging directory')
    if stage.exists():shutil.rmtree(stage)
    stage.mkdir()
    archive=output/f'python-{PYTHON}-embed-amd64.zip'
    if not archive.exists():
        urllib.request.urlretrieve(f'https://www.python.org/ftp/python/{PYTHON}/{archive.name}',archive)
    if hashlib.sha256(archive.read_bytes()).hexdigest()!=PYTHON_SHA256:
        raise RuntimeError('Python runtime SHA-256 mismatch')
    with zipfile.ZipFile(archive) as z:z.extractall(stage/'python')
    deps=stage/'python/Lib/site-packages'
    subprocess.run([sys.executable,'-m','pip','install','--target',str(deps),'--python-version','3.14',
        '--platform','win_amd64','--implementation','cp','--abi','cp314','--only-binary=:all:',
        '--no-compile','-r',str(ROOT/'server/requirements-windows.lock')],check=True)
    (stage/'python/python314._pth').write_text('python314.zip\n.\nLib/site-packages\n../server\n..\nimport site\n')
    for name in ['LICENSE','NOTICE.md','README.md','CHANGELOG.md','run.py','setup.py','Start.cmd','Setup.cmd']:
        shutil.copy2(ROOT/name,stage/name)
    shutil.copytree(ROOT/'docs',stage/'docs')
    (stage/'server').mkdir()
    for p in (ROOT/'server').iterdir():
        if p.is_file() and (p.suffix=='.py' or p.name in ['.env.example','requirements.txt','requirements-windows.lock']):
            shutil.copy2(p,stage/'server'/p.name)
    package=output/f'MultiVeglia-{VERSION}-windows-x64.zip'
    with zipfile.ZipFile(package,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for p in sorted(stage.rglob('*')):
            if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc':
                z.write(p,Path(f'MultiVeglia-{VERSION}')/p.relative_to(stage))
    print(package)


if __name__=='__main__':main()
