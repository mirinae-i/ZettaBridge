#!/usr/bin/env python3
"""Build Test10 over pinned Test9 with native screen mode and reduced tracing overhead."""
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

BASE_SHA256 = '89cb8da5046d953ecced711e5f068a93cf5a3ec1afe17bb0369da858d4f70208'

def main(*, base_sha=BASE_SHA256, base_report=b'zettabridge-diagnostic-report 9',
         revision=10, suffix='native-screen', direct_launch=False):
    version_code = 20261009 + revision
    version_name = f'0.1.0-blockheads-test{revision}-{suffix}'
    report_header = f'zettabridge-diagnostic-report{revision}'.encode('ascii')
    assert len(base_report) == len(report_header)
    parser = argparse.ArgumentParser(description=f"Build Test{revision} over its pinned input APK ({suffix}).")
    for name in ['base', 'native', 'jdk', 'sdk', 'audit-dir', 'signing', 'work', 'out']:
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    for name, value in vars(args).items(): setattr(args, name, value.resolve())
    assert hashlib.sha256(args.base.read_bytes()).hexdigest() == base_sha
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
    stubs = sorted((repo / 'android/test5/compile-stubs').rglob('*.java'))
    sources = [repo / 'android/test8/Test8Application.java']
    if direct_launch:
        stubs += sorted((repo / 'android/test11/compile-stubs').rglob('*.java'))
        sources.append(repo / 'android/test11/BlockheadsLaunchActivity.java')
    run(compiler + ['-classpath', android, '-d', stub_classes] + stubs)
    run(compiler + ['-classpath', str(android) + os.pathsep + str(stub_classes), '-d', app_classes] + sources)
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
        root.set(key('versionCode'), str(version_code))
        root.set(key('versionName'), version_name)
        app = root.find('application')
        app.set(key('name'), 'com.zettabridge.launcher.Test8Application')
        app.set(key('label'), f'ZettaBridge Blockheads Test {revision}')
        if direct_launch:
            app.set(key('label'), 'Blockheads - ZettaBridge')
            app.set(key('icon'), '@mipmap/ic_launcher')
            app.set(key('roundIcon'), '@mipmap/ic_launcher')
            library = next(a for a in app.findall('activity')
                           if a.get(key('name')) == 'com.zettabridge.launcher.LibraryActivity')
            for intent_filter in list(library.findall('intent-filter')):
                if any(c.get(key('name')) == 'android.intent.category.LAUNCHER'
                       for c in intent_filter.findall('category')):
                    library.remove(intent_filter)
            library.set(key('label'), 'ZettaBridge Settings')
            entry = ET.SubElement(app, 'activity', {
                key('name'): 'com.zettabridge.launcher.BlockheadsLaunchActivity',
                key('exported'): 'true', key('theme'): '@android:style/Theme.NoDisplay',
                key('taskAffinity'): package + '.entry', key('excludeFromRecents'): 'true',
            })
            intent_filter = ET.SubElement(entry, 'intent-filter')
            ET.SubElement(intent_filter, 'action', {key('name'): 'android.intent.action.MAIN'})
            ET.SubElement(intent_filter, 'category', {key('name'): 'android.intent.category.LAUNCHER'})
            ET.SubElement(entry, 'meta-data', {key('name'): 'android.app.shortcuts',
                                              key('resource'): '@xml/shortcuts'})
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
        link = [bt / 'aapt2', 'link', '-I', android, '--manifest', manifest, '-o', unsigned]
        if direct_launch:
            resources = args.work / 'resources.zip'
            resources.unlink(missing_ok=True)
            run([bt / 'aapt2', 'compile', '--dir', repo / 'android/test11/res', '-o', resources])
            link.append(resources)
        run(link)
        with zipfile.ZipFile(unsigned, 'a', zipfile.ZIP_DEFLATED) as output:
            for info in base.infolist():
                name = info.filename
                if name in ('AndroidManifest.xml', 'resources.arsc', 'classes2.dex') or name.startswith('META-INF/'): continue
                data = base.read(name)
                if name == 'classes.dex':
                    assert data.count(base_report) == 1
                    assert old_package == package, 'The diagnostic package must update in place'
                    data = bytearray(data.replace(base_report, report_header))
                    # Test6 canonical-path fix must remain intact.
                    assert data[0xc870:0xc87c] == bytes.fromhex('6e10450200000c005b100e00')
                    data[12:32] = hashlib.sha1(data[32:]).digest()
                    struct.pack_into('<I', data, 8, zlib.adler32(data[12:]) & 0xffffffff)
                elif name == 'lib/arm64-v8a/libzbridge.so': data = args.native.read_bytes()
                output.writestr(name, data)
            output.writestr('classes2.dex', (dex / 'classes.dex').read_bytes())
            output.writestr(f'assets/licenses/TEST{revision}-NOTICE.txt',
                'Unofficial compatibility test build; not a native ARM64 game port.\n'
                'Core base: ZailoxTT/ZettaBridge d6066b9b9e61de27041ba6e1f3c499c080c9e2b7.\n'
                f'Test{revision}: native screen mode, reduced tracing cost, and bounded display policy. Prior runtime assets retained.\n'
                + ('Direct-launch addon and original vector launcher artwork included.\n' if direct_launch else '') +
                'Source, reproduction evidence and rebuild instructions accompany this APK.\n'
                'PolyForm Noncommercial 1.0.0 and Perimeter 1.0.1 apply cumulatively.\n'
                'Game execution on the target Android device has not been verified.\n')
    aligned = args.work / 'aligned.apk'
    run([bt / 'zipalign', '-f', '-P', '16', '4', unsigned, aligned])
    secret = serialization.load_pem_private_key((args.signing / 'experimental-key.pem').read_bytes(), password=None)
    key_file = args.work / 'test-key.pk8'
    key_file.touch(mode=0o600, exist_ok=True)
    key_file.chmod(0o600)
    key_file.write_bytes(secret.private_bytes(serialization.Encoding.DER, serialization.PrivateFormat.PKCS8,
                                             serialization.NoEncryption()))
    key_file.chmod(0o600)
    signer = [java, '-jar', bt / 'lib/apksigner.jar']
    try:
        run(signer + ['sign', '--key', key_file, '--cert', args.signing / 'experimental-cert.pem',
                  '--v1-signing-enabled', 'true', '--v2-signing-enabled', 'true', '--v3-signing-enabled', 'false',
                  '--v4-signing-enabled', 'false', '--out', args.out, aligned])
    finally:
        key_file.unlink(missing_ok=True)
    run(signer + ['verify', '--verbose', '--print-certs', args.out])
    run([bt / 'zipalign', '-c', '-P', '16', '4', args.out])
    result = dict(package=package, size=args.out.stat().st_size,
                  sha256=hashlib.sha256(args.out.read_bytes()).hexdigest(), input_base_sha256=base_sha,
                  android_device_tested=False, separate_install=False, update_from_version=revision - 1,
                  native_sha256=hashlib.sha256(args.native.read_bytes()).hexdigest(),
                  source_commit=subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip())
    args.out.with_suffix('.build.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))

if __name__ == '__main__': main()
