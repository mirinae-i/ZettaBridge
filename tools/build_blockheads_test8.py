#!/usr/bin/env python3
"""Build Test8 as a signed update to Test7, adding owner-thread configuration dispatch and display diagnostics."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile
import zlib
from cryptography.hazmat.primitives import serialization

BASE_SHA256 = 'b199fd2e8e8b084f64e49c97483b019ff2673e4b0c84c7bbcbc98e23db0c7fcf'

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['base', 'native', 'jdk', 'sdk', 'audit-dir', 'signing', 'work', 'out']:
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    for name, value in vars(args).items(): setattr(args, name, value.resolve())
    assert hashlib.sha256(args.base.read_bytes()).hexdigest() == BASE_SHA256
    repo = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(args.audit_dir))
    from audit_apk import parse_axml
    args.work.mkdir(parents=True, exist_ok=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.work / 'tmp'; tmp.mkdir(exist_ok=True)
    bt = args.sdk / 'build-tools/35.0.0'
    android = args.sdk / 'platforms/android-35/android.jar'
    env = os.environ.copy()
    env.update(JAVA_HOME=str(args.jdk), TMPDIR=str(tmp))
    env['LD_LIBRARY_PATH'] = str(args.jdk / 'lib') + os.pathsep + str(bt / 'lib64')
    def run(command): subprocess.run([str(x) for x in command], env=env, check=True, cwd=args.work)
    def jar(path, folder):
        with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as archive:
            for file in sorted(folder.rglob('*.class')): archive.write(file, file.relative_to(folder).as_posix())
    stub_classes = args.work / 'stub-classes'
    app_classes = args.work / 'app-classes'
    dex = args.work / 'dex'
    for folder in [stub_classes, app_classes, dex]:
        if folder.exists(): shutil.rmtree(folder)
        folder.mkdir()
    compiler = [args.jdk / 'bin/javac', '-J-Djava.io.tmpdir=' + str(tmp), '-encoding', 'UTF-8',
                '-source', '17', '-target', '17']
    run(compiler + ['-classpath', android, '-d', stub_classes] +
        sorted((repo / 'android/test5/compile-stubs').rglob('*.java')))
    run(compiler + ['-classpath', str(android) + os.pathsep + str(stub_classes), '-d', app_classes,
                    repo / 'android/test8/Test8Application.java'])
    jar(args.work / 'compile-stubs.jar', stub_classes)
    jar(args.work / 'test8.jar', app_classes)
    java = args.jdk / 'bin/java'
    run([java, '-Djava.io.tmpdir=' + str(tmp), '-cp', bt / 'lib/d8.jar', 'com.android.tools.r8.D8',
         '--release', '--min-api', '26', '--lib', android, '--classpath', args.work / 'compile-stubs.jar',
         '--output', dex, args.work / 'test8.jar'])

    ns = 'http://schemas.android.com/apk/res/android'
    key = lambda name: '{' + ns + '}' + name
    ET.register_namespace('android', ns)
    with zipfile.ZipFile(args.base) as base:
        root = parse_axml(base.read('AndroidManifest.xml'))
        old_package = root.get('package')
        package = 'com.zettabridge.blockheadstest5'
        root.set('package', package)
        root.set(key('versionCode'), '20261017')
        root.set(key('versionName'), '0.1.0-blockheads-test8-display-threads')
        app = root.find('application')
        app.set(key('name'), 'com.zettabridge.launcher.Test8Application')
        app.set(key('label'), 'ZettaBridge Blockheads Test 8')
        references = {
            '@0x01080093': '@android:drawable/sym_def_app_icon',
            '@0x01030238': '@android:style/Theme.Material.Light.DarkActionBar',
            '@0x01030010': '@android:style/Theme.Translucent.NoTitleBar',
            '@0x01030055': '@android:style/Theme.NoDisplay',
            '@0x0103022e': '@android:style/Theme.Material.NoActionBar',
        }
        configs = 'mcc|mnc|locale|touchscreen|keyboard|keyboardHidden|navigation|screenLayout|fontScale|uiMode|orientation|density|screenSize|smallestScreenSize|layoutDirection|colorMode'
        for node in root.iter():
            for attr, value in list(node.attrib.items()):
                if value in references: node.set(attr, references[value])
                elif attr == key('configChanges') and value == '0x40007fff': node.set(attr, configs)
                elif attr == key('launchMode'):
                    node.set(attr, {'0': 'standard', '1': 'singleTop', '2': 'singleTask', '3': 'singleInstance'}[value])
                elif attr == key('screenOrientation'):
                    node.set(attr, {'6': 'sensorLandscape', '7': 'sensorPortrait'}[value])
                elif attr == key('taskAffinity'): node.set(attr, value.replace(old_package, package))
        manifest = args.work / 'AndroidManifest.xml'
        ET.ElementTree(root).write(manifest, encoding='utf-8', xml_declaration=True)
        unsigned = args.work / 'unsigned.apk'
        if unsigned.exists(): unsigned.unlink()
        run([bt / 'aapt2', 'link', '-I', android, '--manifest', manifest, '-o', unsigned])
        with zipfile.ZipFile(unsigned, 'a', zipfile.ZIP_DEFLATED) as output:
            for info in base.infolist():
                name = info.filename
                if name in ('AndroidManifest.xml', 'resources.arsc', 'classes2.dex') or name.startswith('META-INF/'): continue
                data = base.read(name)
                if name == 'classes.dex':
                    assert data.count(b'zettabridge-diagnostic-report 7') == 1
                    assert old_package == package, 'Test8 must update Test7 in place'
                    data = bytearray(data.replace(b'zettabridge-diagnostic-report 7', b'zettabridge-diagnostic-report 8'))
                    # Test6 canonical-path fix must remain intact.
                    assert data[0xc870:0xc87c] == bytes.fromhex('6e10450200000c005b100e00')
                    data[12:32] = hashlib.sha1(data[32:]).digest()
                    struct.pack_into('<I', data, 8, zlib.adler32(data[12:]) & 0xffffffff)
                elif name == 'lib/arm64-v8a/libzbridge.so': data = args.native.read_bytes()
                output.writestr(name, data)
            output.writestr('classes2.dex', (dex / 'classes.dex').read_bytes())
            output.writestr('assets/licenses/TEST8-NOTICE.txt',
                'Unofficial compatibility test build; not a native ARM64 game port.\n'
                'Core base: ZailoxTT/ZettaBridge d6066b9b9e61de27041ba6e1f3c499c080c9e2b7.\n'
                'Test7 primary DEX and runtime assets retained. Test8 addon and core add display diagnostics and configuration dispatch.\n'
                'Source, reproduction evidence and rebuild instructions accompany this APK.\n'
                'PolyForm Noncommercial 1.0.0 and Perimeter 1.0.1 apply cumulatively.\n'
                'Game execution on the target Android device has not been verified.\n')
    aligned = args.work / 'aligned.apk'
    run([bt / 'zipalign', '-f', '-P', '16', '4', unsigned, aligned])
    secret = serialization.load_pem_private_key((args.signing / 'experimental-key.pem').read_bytes(), password=None)
    key_file = args.work / 'test-key.pk8'
    key_file.write_bytes(secret.private_bytes(serialization.Encoding.DER, serialization.PrivateFormat.PKCS8,
                                             serialization.NoEncryption()))
    key_file.chmod(0o600)
    signer = [java, '-jar', bt / 'lib/apksigner.jar']
    run(signer + ['sign', '--key', key_file, '--cert', args.signing / 'experimental-cert.pem',
                  '--v1-signing-enabled', 'true', '--v2-signing-enabled', 'true', '--v3-signing-enabled', 'false',
                  '--v4-signing-enabled', 'false', '--out', args.out, aligned])
    run(signer + ['verify', '--verbose', '--print-certs', args.out])
    run([bt / 'zipalign', '-c', '-P', '16', '4', args.out])
    result = dict(package=package, size=args.out.stat().st_size,
                  sha256=hashlib.sha256(args.out.read_bytes()).hexdigest(), input_test7_sha256=BASE_SHA256,
                  android_device_tested=False, separate_install=False, update_from_test7=True,
                  native_sha256=hashlib.sha256(args.native.read_bytes()).hexdigest(),
                  source_commit=subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip())
    args.out.with_suffix('.build.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))

if __name__ == '__main__': main()
