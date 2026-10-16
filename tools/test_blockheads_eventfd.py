#!/usr/bin/env python3
"""Run ARM32 eventfd/Apportable regressions through before/after ARM64 cores.

QEMU executes the ARM64 development runner only; it is never packaged in an APK.
The original game must be provided separately. No game constructor is disabled.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import zipfile

from fix_guest_lib import fix

GAME_SHA = 'cae0371354dfda125793ba974c1f7a55b2161ed6d9c458f962da9eb468f8ec54'
TEST8_SHA = 'bacce4296ed8c398742090b0caa0475212ae77fb24f87757c5dfab155b47010c'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('game', 'base', 'ndk-bin', 'qemu', 'before', 'after', 'out'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    for name, value in vars(args).items(): setattr(args, name, value.resolve())
    assert hashlib.sha256(args.game.read_bytes()).hexdigest() == GAME_SHA
    assert hashlib.sha256(args.base.read_bytes()).hexdigest() == TEST8_SHA
    args.out.mkdir(parents=True, exist_ok=True)
    tmp = args.out / 'tmp'; tmp.mkdir(exist_ok=True)
    libraries = args.out / 'libraries'; libraries.mkdir(exist_ok=True)
    fixes = {}
    with zipfile.ZipFile(args.game) as archive:
        for name in archive.namelist():
            if name.startswith('lib/armeabi-v7a/') and name.endswith('.so'):
                dest = libraries / Path(name).name
                dest.write_bytes(archive.read(name))
                fixes[dest.name] = fix(dest)
                assert not fixes[dest.name].startswith(('skip', 'error'))
    assert len(fixes) == 25
    with zipfile.ZipFile(args.base) as archive:
        for name in archive.namelist():
            if name.startswith('assets/zb/') and not name.endswith('/'):
                relative = Path(name[7:])
                assert '..' not in relative.parts
                dest = args.out / relative
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(archive.read(name))
    repo = Path(__file__).resolve().parents[1]
    env = dict(os.environ, TMPDIR=str(tmp))
    programs = {}
    for name, source in [('eventfd', 'eventfd_legacy_dynamic.c'),
                         ('dispatch', 'blockheads_dispatch_dynamic.c')]:
        binary = args.out / name
        subprocess.run([str(args.ndk_bin / 'armv7a-linux-androideabi21-clang'),
                        '-O2', '-Wall', '-Wextra', str(repo / 'guest/tests' / source),
                        '-ldl', '-o', str(binary)], env=env, check=True)
        programs[name] = binary
    guest_env = {
        'LD_LIBRARY_PATH': f'{args.out}/zb/guest/lib:{libraries}',
        'PACKAGE_CODE_PATH': str(args.game), 'PACKAGE_RESOURCE_PATH': str(args.game),
        'PACKAGE_NAME': 'com.noodlecake.blockheads',
        'CFProcessPath': f'{args.game}/com.noodlecake.blockheads',
        'CACHEDIR': str(tmp), 'TMPDIR': str(tmp), 'CFFIXED_USER_HOME': str(tmp),
        'ANDROID_DATA_DIRECTORY': '/data', 'ANDROID_EXTERNAL_STORAGE': '/sdcard',
        'LOCALE': 'en_US', 'LANGUAGES': 'en', 'TZ': 'UTC',
    }
    results = {}
    for version, runner in [('before', args.before), ('after', args.after)]:
        for name, program in programs.items():
            command = [args.qemu, runner, '--sysroot', args.out / 'zb/sysroot']
            for key, value in guest_env.items(): command += ['--env', f'{key}={value}']
            command += [program]
            label = f'{version}-{name}'
            with (args.out / f'{label}.log').open('w') as log:
                result = subprocess.run([str(x) for x in command], stdout=log,
                                        stderr=subprocess.STDOUT, timeout=45,
                                        env=dict(env, ZB_LOAD_TRACE='1'))
            output = (args.out / f'{label}.log').read_text()
            if version == 'before':
                ok = result.returncode == 1 and 'unimplemented syscall eventfd (351)' in output
                if name == 'dispatch': ok = ok and 'RESULT immediate=1 delayed=0' in output
            else:
                ok = result.returncode == 0 and 'PASS' in output
                if name == 'dispatch': ok = ok and 'RESULT immediate=1 delayed=1' in output
                ok = ok and 'unimplemented syscall eventfd' not in output
            results[label] = dict(returncode=result.returncode, expected_result=ok)
            print(label, json.dumps(results[label]), flush=True)
            if not ok: print(output[-6000:], flush=True)
    summary = dict(results=results, passed=all(v['expected_result'] for v in results.values()),
                   original_game_sha256=GAME_SHA, test8_apk_sha256=TEST8_SHA,
                   before_runner_sha256=hashlib.sha256(args.before.read_bytes()).hexdigest(),
                   after_runner_sha256=hashlib.sha256(args.after.read_bytes()).hexdigest(),
                   import_fixups=fixes, constructors_retained=True,
                   android_ui_executed=False, world_generation_verified=False)
    (args.out / 'results.json').write_text(json.dumps(summary, indent=2) + '\n')
    if not summary['passed']: raise SystemExit(1)


if __name__ == '__main__': main()
