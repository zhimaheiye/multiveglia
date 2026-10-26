"""Build a release APK using Android SDK 34 and JDK 17; never generates keys."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-tools',type=Path,required=True)
    parser.add_argument('--android-jar',type=Path,required=True)
    parser.add_argument('--java-home',type=Path,required=True)
    parser.add_argument('--keystore',type=Path,required=True)
    parser.add_argument('--alias',default='multiveglia')
    parser.add_argument('--output',type=Path,default=Path(__file__).parent/'MultiVeglia.apk')
    args=parser.parse_args()
    if not os.environ.get('VEGLIA_KEYSTORE_PASSWORD'):
        parser.error('Set VEGLIA_KEYSTORE_PASSWORD in the environment (never on the command line).')
    root=Path(__file__).resolve().parent
    out=root/'build'
    # Only remove this script's own fixed build directory, never an argument.
    if out.resolve().parent != root or out.is_symlink():
        raise RuntimeError('Unsafe build directory')
    if out.exists():shutil.rmtree(out)
    for name in ['gen','classes','res','apk']:(out/name).mkdir(parents=True)
    src=root/'app/src/main'
    java=args.java_home.resolve()/'bin'
    bt=args.build_tools.resolve()
    env={**os.environ,'JAVA_HOME':str(args.java_home.resolve()),'PATH':str(java)+os.pathsep+os.environ['PATH']}
    def run(*argv):subprocess.run([str(x) for x in argv],check=True,env=env)
    def tool(name):
        suffix=('.bat' if name in ['d8','apksigner'] else '.exe') if os.name=='nt' else ''
        return bt/(name+suffix)
    def jtool(name):return java/(name+('.exe' if os.name=='nt' else ''))
    unsigned=out/'apk/app.unsigned.apk';aligned=out/'apk/app.aligned.apk'
    run(tool('aapt2'),'compile','--dir',src/'res','-o',out/'res')
    run(tool('aapt2'),'link','-o',unsigned,'-I',args.android_jar.resolve(),
        '--manifest',src/'AndroidManifest.xml','--java',out/'gen','--auto-add-overlay',*sorted((out/'res').glob('*.flat')))
    sources=[*sorted((src/'java').rglob('*.java')),*sorted((out/'gen').rglob('*.java'))]
    run(jtool('javac'),'-encoding','UTF-8','-source','11','-target','11','-classpath',args.android_jar.resolve(),'-d',out/'classes',*sources)
    run(jtool('jar'),'cf',out/'classes.jar','-C',out/'classes','.')
    run(tool('d8'),'--output',out/'apk','--lib',args.android_jar.resolve(),out/'classes.jar')
    run(jtool('jar'),'uf',unsigned,'-C',out/'apk','classes.dex')
    run(tool('zipalign'),'-f','4',unsigned,aligned)
    args.output.resolve().parent.mkdir(parents=True,exist_ok=True)
    run(tool('apksigner'),'sign','--ks',args.keystore.resolve(),'--ks-key-alias',args.alias,
        '--ks-pass','env:VEGLIA_KEYSTORE_PASSWORD','--key-pass','env:VEGLIA_KEYSTORE_PASSWORD',
        '--out',args.output.resolve(),aligned)
    run(tool('apksigner'),'verify','--verbose','--print-certs',args.output.resolve())
    print('Release APK:',args.output.resolve())


if __name__=='__main__':main()
