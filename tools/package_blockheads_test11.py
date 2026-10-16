#!/usr/bin/env python3
"""Package the verified APK, rebuild inputs/source and evidence; never signing keys."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

from build_blockheads_test11 import BASE_SHA256


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('apk', 'base', 'proof', 'readme', 'out'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]

    def git(*command):
        return subprocess.check_output(['git', '-C', str(repo), *command])

    subprocess.run(['git', '-C', str(repo), 'diff', '--exit-code', '--ignore-submodules=all', 'HEAD'], check=True)
    assert not git('ls-files', '--others', '--exclude-standard').strip(), 'commit new source files first'
    head = git('rev-parse', 'HEAD').decode().strip()
    tree = git('rev-parse', 'HEAD^{tree}').decode().strip()
    build = json.loads(args.apk.with_suffix('.build.json').read_text())
    verified = json.loads((args.proof / 'apk-verification.json').read_text())
    apk = args.apk.read_bytes()
    digest = hashlib.sha256(apk).hexdigest()
    assert build['source_commit'] == head, 'build from the committed source before packaging'
    assert build['sha256'] == verified['apk_sha256'] == digest and verified['checks_passed']
    assert hashlib.sha256(args.base.read_bytes()).hexdigest() == BASE_SHA256
    files = {
        'ZettaBridge-Blockheads-Test11-arm64.apk': apk,
        'README-ko.txt': args.readme.read_bytes(),
        'source/inputs/Test10-base.apk': args.base.read_bytes(),
        'source/ZettaBridge-source.tar.gz': git('archive', '--format=tar.gz', '--prefix=ZettaBridge/', 'HEAD'),
        'source/REVISION.json': (json.dumps(dict(commit=head, tree=tree,
            repository='https://github.com/mirinae-i/ZettaBridge', branch='develop',
            base_sha256=BASE_SHA256, apk_sha256=digest,
            dynarmic_commit='86458a0bd369d63ba4c2ef812cacbb6c9080c065',
            dynarmic_patches=['dynarmic-0001-thumb32-armv8.patch', 'dynarmic-0002-asimd-narrowing.patch'],
            android_device_tested=False), indent=2) + '\n').encode(),
        'proof/' + args.apk.with_suffix('.build.json').name: args.apk.with_suffix('.build.json').read_bytes(),
    }
    for name in ('apk-verification.json', 'apk-build.log', 'apk-badging.txt', 'apk-resources.txt',
                 'native-configure.log', 'native-build.log', 'native-build-retry.log', 'native-build-final.log',
                 'display-contracts.log', 'launch-contracts.log', 'native-screen-guards.log', 'native-layout.json',
                 'icon-preview.png'):
        files['proof/' + name] = (args.proof / name).read_bytes()
    checksums = ''.join(hashlib.sha256(data).hexdigest() + '  ' + name + '\n'
                        for name, data in sorted(files.items()))
    files['SHA256SUMS.txt'] = checksums.encode()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.out, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(files.items()):
            archive.writestr(name, data)
    with zipfile.ZipFile(args.out) as archive:
        assert archive.testzip() is None
        assert all(archive.read(name) == data for name, data in files.items())
    print(json.dumps(dict(zip=str(args.out), bytes=args.out.stat().st_size,
                          sha256=hashlib.sha256(args.out.read_bytes()).hexdigest(),
                          source_commit=head, apk_sha256=digest), indent=2))


if __name__ == '__main__':
    main()
