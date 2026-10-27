#!/usr/bin/env python3
"""Build a scoped, importable guest fix without re-signing the Test12 launcher.

Requires the user-supplied guest2 APK, Apktool 2.11.1, JDK17 and SDK build-tools35.
The game and signing key are never repository inputs. Only three surface methods
change; a small independently compiled helper is added in classes4.dex.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import zipfile

INPUT_SHA = 'db72a693c59a930e311869b8989a4fc61d6c5699c161915025096ce045b40fac'
TARGET = 'com/apportable/gl/GLSurfaceView.smali'
METHODS = ('readySurface', 'surfaceCreated', 'surfaceDestroyed')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def method_text(text, name):
    matches = re.findall(r'(?m)^\.method public ' + name + r'\(\)V\n.*?^\.end method', text, re.S)
    if len(matches) != 1:
        raise ValueError('Expected one method: ' + name)
    return matches[0]


def patch_surface(text, source, compiled_ready):
    ready = method_text(text, 'readySurface')
    # Match the original monitor-wait site, including its exception handlers.
    start = ready.index('    :cond_6\n')
    end = ready.index('    :cond_7\n', start)
    old = ready[start:end]
    assert old.count('Ljava/lang/Object;->wait()V') == 1
    assert '.locals 7' in ready and 'monitor-enter v6' in ready
    assert '.catchall {:try_start_4 .. :try_end_4} :catchall_0' in old
    assert old.count(':catch_1') == 2
    # Use javac/D8-generated monitor regions instead of hand-editing their CFG.
    text = text.replace(ready, compiled_ready)
    for name in METHODS[1:]:
        old = method_text(text, name)
        assert old.count('Ljava/lang/Object;->wait()V') == 1
        assert 'monitor-enter v1' in old and 'Ljava/lang/Thread;->interrupt()V' in old
        text = text.replace(old, (source / (name + '.smali')).read_text().strip())
    return text


def without_changed_methods(text):
    for name in METHODS:
        text = text.replace(method_text(text, name), '<' + name + '>')
    return text


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for n in ('input', 'apktool', 'java', 'build-tools', 'key', 'cert', 'work', 'out'):
        p.add_argument('--' + n, type=Path, required=True)
    a = p.parse_args()
    for k, v in vars(a).items():
        setattr(a, k, v.resolve())
    assert digest(a.input.read_bytes()) == INPUT_SHA, 'unsupported input; no best-effort patch'
    assert not a.work.exists(), 'Use a new work directory for a reviewable build'
    a.work.mkdir(parents=True)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    repo = Path(__file__).resolve().parents[1]
    source = repo / 'android/guest-resume'
    tmp = a.work / 'tmp'; tmp.mkdir()
    java = [str(a.java), '-Djava.io.tmpdir=' + str(tmp)]
    env = os.environ.copy()

    def run(cmd):
        subprocess.run([str(x) for x in cmd], env=env, check=True)

    decoded = a.work / 'decoded'
    run(java + ['-jar', a.apktool, 'd', '-r', '-o', decoded, a.input])
    surface = decoded / 'smali' / TARGET
    original = surface.read_text()
    stubs = a.work / 'stubs'; stubs.mkdir()
    for name, body in {
        'MainThread.java': 'package com.apportable; public class MainThread { public static native Thread getThread(); }',
        'RunLoop.java': 'package com.apportable.utils; public class RunLoop { public static native void processMessages(); }',
        'SurfaceHolder.java': 'package android.view; public interface SurfaceHolder { }',
        'GL.java': 'package javax.microedition.khronos.opengles; public interface GL { }',
        'GL10.java': 'package javax.microedition.khronos.opengles; public interface GL10 extends GL { }',
        'EGLConfig.java': 'package javax.microedition.khronos.egl; public class EGLConfig { }',
        'GLSurfaceView.java': 'package android.opengl; public class GLSurfaceView { public interface Renderer { void onSurfaceCreated(javax.microedition.khronos.opengles.GL10 gl, javax.microedition.khronos.egl.EGLConfig config); void onSurfaceChanged(javax.microedition.khronos.opengles.GL10 gl, int width, int height); } }',
    }.items():
        (stubs / name).write_text(body + '\n')
    stubclasses = a.work / 'stub-classes'; stubclasses.mkdir()
    classes = a.work / 'classes'; classes.mkdir()
    run(java + ['com.sun.tools.javac.Main', '--release', '8', '-d', stubclasses] + sorted(stubs.glob('*.java')))
    run(java + ['com.sun.tools.javac.Main', '--release', '8', '-cp', stubclasses, '-d', classes, source / 'SurfaceWait.java'])
    helperjar = a.work / 'helper.jar'
    stubjar = a.work / 'stubs.jar'
    for path, folder in ((helperjar, classes), (stubjar, stubclasses)):
        with zipfile.ZipFile(path, 'w') as z:
            for f in sorted(folder.rglob('*.class')):
                z.write(f, f.relative_to(folder).as_posix())
    dex = a.work / 'dex'; dex.mkdir()
    run(java + ['-cp', a.build_tools / 'lib/d8.jar', 'com.android.tools.r8.D8', '--release',
                '--min-api', '26', '--classpath', stubjar, '--output', dex, helperjar])

    methodsrc = a.work / 'method-source'; methodsrc.mkdir()
    (methodsrc / 'GLSurfaceView.java').write_text((source / 'GLSurfaceView.java.in').read_text())
    methodclasses = a.work / 'method-classes'; methodclasses.mkdir()
    run(java + ['com.sun.tools.javac.Main', '--release', '8', '-cp',
                os.pathsep.join([str(stubclasses), str(classes)]), '-d', methodclasses,
                methodsrc / 'GLSurfaceView.java'])
    methodjar = a.work / 'method.jar'
    with zipfile.ZipFile(methodjar, 'w') as z:
        for f in sorted(methodclasses.rglob('*.class')):
            z.write(f, f.relative_to(methodclasses).as_posix())
    methoddex = a.work / 'method-dex'; methoddex.mkdir()
    run(java + ['-cp', a.build_tools / 'lib/d8.jar', 'com.android.tools.r8.D8', '--release',
                '--min-api', '26', '--classpath', stubjar, '--classpath', helperjar,
                '--output', methoddex, methodjar])
    methodapk = a.work / 'method.apk'
    with zipfile.ZipFile(methodapk, 'w') as z, zipfile.ZipFile(a.input) as old:
        z.writestr('AndroidManifest.xml', old.read('AndroidManifest.xml'))
        z.writestr('classes.dex', (methoddex / 'classes.dex').read_bytes())
    methoddecoded = a.work / 'method-decoded'
    run(java + ['-jar', a.apktool, 'd', '-r', '-o', methoddecoded, methodapk])
    compiled_ready = method_text((methoddecoded / 'smali' / TARGET).read_text(), 'readySurface')
    changed = patch_surface(original, source, compiled_ready)
    assert without_changed_methods(original) == without_changed_methods(changed)
    surface.write_text(changed)
    rebuilt = a.work / 'rebuilt.apk'
    run(java + ['-jar', a.apktool, 'b', decoded, '-o', rebuilt])

    unsigned = a.work / 'unsigned.apk'
    with zipfile.ZipFile(a.input) as old, zipfile.ZipFile(rebuilt) as new, \
            zipfile.ZipFile(unsigned, 'w') as out:
        assert 'classes4.dex' not in old.namelist()
        for entry in old.infolist():
            if entry.filename.startswith('META-INF/'):
                continue
            data = new.read('classes.dex') if entry.filename == 'classes.dex' else old.read(entry.filename)
            out.writestr(entry, data)
        out.writestr('classes4.dex', (dex / 'classes.dex').read_bytes(), compress_type=zipfile.ZIP_DEFLATED)
        out.writestr('assets/ZETTABRIDGE-GUEST3.txt',
                     'Guest3: bounded owner-message pumping while waiting for a surface.\n'
                     'Import into the existing Test12 launcher; do not uninstall the launcher.\n'
                     'Game resources, native libraries and PendingIntent fix are preserved.\n'
                     'Unofficial local compatibility patch. Target-device confirmation required.\n')
    aligned = a.work / 'aligned.apk'
    run([a.build_tools / 'zipalign', '-f', '-P', '16', '4', unsigned, aligned])
    signer = java + ['-jar', a.build_tools / 'lib/apksigner.jar']
    run(signer + ['sign', '--key', a.key, '--cert', a.cert, '--v1-signing-enabled', 'true',
                 '--v2-signing-enabled', 'true', '--v3-signing-enabled', 'false',
                 '--v4-signing-enabled', 'false', '--out', a.out, aligned])
    run(signer + ['verify', '--verbose', '--print-certs', a.out])
    run([a.build_tools / 'zipalign', '-c', '-P', '16', '4', a.out])

    # Decode the assembled file again. Compare symbolic instructions, annotations,
    # access flags and debug info for every primary-DEX class outside the three edits.
    checked = a.work / 'checked'
    run(java + ['-jar', a.apktool, 'd', '-r', '-o', checked, a.out])
    before_files = {f.relative_to(decoded / 'smali').as_posix(): f for f in (decoded / 'smali').rglob('*.smali')}
    after_files = {f.relative_to(checked / 'smali').as_posix(): f for f in (checked / 'smali').rglob('*.smali')}
    assert before_files.keys() == after_files.keys()
    assert compiled_ready == method_text(after_files[TARGET].read_text(), 'readySurface')
    helper_files = list((checked / 'smali_classes4').rglob('*.smali'))
    assert len(helper_files) == 1 and helper_files[0].name == 'SurfaceWait.smali'
    for name, f in before_files.items():
        left, right = f.read_text(), after_files[name].read_text()
        if name == TARGET:
            left, right = without_changed_methods(left), without_changed_methods(right)
        assert left == right, 'Unexpected DEX change: ' + name
    preserved = []
    with zipfile.ZipFile(a.input) as old, zipfile.ZipFile(a.out) as new:
        assert new.testzip() is None
        assert len(new.namelist()) == len(set(new.namelist()))
        for n in old.namelist():
            if n == 'classes.dex' or n.startswith('META-INF/'):
                continue
            assert old.read(n) == new.read(n), n
            preserved.append(n)
        assert set(new.namelist()) - set(old.namelist()) - {'classes4.dex', 'assets/ZETTABRIDGE-GUEST3.txt'} <= \
               {n for n in new.namelist() if n.startswith('META-INF/')}
    result = dict(input_sha256=INPUT_SHA, apk_sha256=digest(a.out.read_bytes()),
                  primary_dex_classes=len(before_files), changed_methods=list(METHODS),
                  preserved_zip_members=len(preserved), native_libraries_unchanged=True,
                  compiled_ready_method_matches=True, manifest_unchanged=True,
                  launcher_apk_unchanged=True, android_device_tested=False)
    a.out.with_suffix('.build.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
