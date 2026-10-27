#!/usr/bin/env python3
"""Build Guest4 from the verified Guest3 APK, retaining the Test12 launcher.

Requires keystone-engine 0.9.2, pyelftools, JDK17 and Android build-tools35.
Only the supported libApplication.so image and signatures change; a Guest4
marker asset is added. Guest3 DEX, PendingIntent compatibility, game assets
and manifest remain byte-identical.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import struct
import subprocess
import zipfile
from elftools.elf.elffile import ELFFile
from keystone import Ks, KS_ARCH_ARM, KS_MODE_ARM, KS_MODE_LITTLE_ENDIAN

INPUT_SHA = '4b680893ae1fd30374faceb7a19785b2bacb1ae7d5bf68271420b38f0cf4d55c'
LIB_SHA = '733d821027d69de329d0ba171df2e6013d612edf5a4d327badd001acc30b94c7'
LIB_PATH = 'lib/armeabi-v7a/libApplication.so'
HOOK = 0x26d860
CONTINUATION = HOOK + 4
CAVE = 0xe31d00
NEXT_SEGMENT = 0xe32000


def sha(data):
    return hashlib.sha256(data).hexdigest()


def patch_library(raw):
    if sha(raw) != LIB_SHA:
        raise ValueError('Unsupported game library; refusing a best-effort patch')
    elf = ELFFile(io.BytesIO(raw))
    assert elf.elfclass == 32 and elf.little_endian
    segments = list(elf.iter_segments())
    rx, rw = segments[2], segments[3]
    assert rx['p_type'] == rw['p_type'] == 'PT_LOAD'
    assert rx['p_offset'] == rx['p_vaddr'] == 0 and rx['p_flags'] == 5
    assert rx['p_filesz'] == rx['p_memsz'] == CAVE
    assert rw['p_offset'] == rw['p_vaddr'] == NEXT_SEGMENT
    assert elf['e_phentsize'] == 32 and not any(raw[CAVE:NEXT_SEGMENT])
    for section in elf.iter_sections():
        if section['sh_flags'] & 2 and section['sh_size']:
            assert section['sh_addr'] >= NEXT_SEGMENT or section['sh_addr'] + section['sh_size'] <= CAVE
    assert struct.unpack_from('<I', raw, HOOK)[0] == 0xed0b0a06
    source = Path(__file__).resolve().parents[1] / 'android/guest-ui/native_ui_scale.S'
    ks = Ks(KS_ARCH_ARM, KS_MODE_ARM | KS_MODE_LITTLE_ENDIAN)
    code = bytes(ks.asm(source.read_text(), addr=CAVE)[0])
    assert 0 < len(code) <= NEXT_SEGMENT - CAVE and len(code) % 4 == 0
    branch = bytes(ks.asm('b #0x%x' % CAVE, addr=HOOK)[0])
    assert len(branch) == 4
    image = bytearray(raw)
    image[CAVE:CAVE + len(code)] = code
    image[HOOK:HOOK + 4] = branch
    # Extend the existing executable file segment only into verified zero padding.
    # Its rounded page extent is unchanged; the next data segment cannot overlap.
    ph = elf['e_phoff'] + 2 * elf['e_phentsize']
    struct.pack_into('<II', image, ph + 16, CAVE + len(code), CAVE + len(code))
    allowed = [(ph + 16, ph + 24), (HOOK, HOOK + 4), (CAVE, CAVE + len(code))]
    assert len(image) == len(raw)
    for i, (old, new) in enumerate(zip(raw, image)):
        assert old == new or any(start <= i < end for start, end in allowed)
    return bytes(image), dict(original_sha256=LIB_SHA, patched_sha256=sha(image),
                             hook=hex(HOOK), continuation=hex(CONTINUATION),
                             stub=hex(CAVE), stub_bytes=len(code), changed_ranges=allowed)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('input', 'java', 'build-tools', 'key', 'cert', 'work', 'out'):
        p.add_argument('--' + name, type=Path, required=True)
    args = p.parse_args()
    for k, v in vars(args).items():
        setattr(args, k, v.resolve())
    assert sha(args.input.read_bytes()) == INPUT_SHA, 'Unsupported Guest3 input'
    assert not args.work.exists(), 'Use a new work directory'
    args.work.mkdir(parents=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.input) as z:
        patched, details = patch_library(z.read(LIB_PATH))
    (args.work / 'libApplication.so').write_bytes(patched)
    unsigned = args.work / 'unsigned.apk'
    with zipfile.ZipFile(args.input) as old, zipfile.ZipFile(unsigned, 'w') as new:
        for entry in old.infolist():
            if entry.filename.startswith('META-INF/'):
                continue
            new.writestr(entry, patched if entry.filename == LIB_PATH else old.read(entry.filename))
        new.writestr('assets/ZETTABRIDGE-GUEST4.txt',
                     'Guest4: multiply native-mode UI scale by 0.9 when the existing\n'
                     'Test11/12 PPI policy selected 600 < points <= 682.\n'
                     'Native display pixel dimensions and Guest3 resume DEX are preserved.\n'
                     'Import into the existing Test12 launcher. Target-device confirmation pending.\n')
    tmp = args.work / 'tmp'; tmp.mkdir()
    java = [str(args.java), '-Djava.io.tmpdir=' + str(tmp)]
    aligned = args.work / 'aligned.apk'

    def run(cmd):
        subprocess.run([str(x) for x in cmd], check=True)

    run([args.build_tools / 'zipalign', '-f', '-P', '16', '4', unsigned, aligned])
    signer = java + ['-jar', args.build_tools / 'lib/apksigner.jar']
    run(signer + ['sign', '--key', args.key, '--cert', args.cert,
                 '--v1-signing-enabled', 'true', '--v2-signing-enabled', 'true',
                 '--v3-signing-enabled', 'false', '--v4-signing-enabled', 'false',
                 '--out', args.out, aligned])
    run(signer + ['verify', '--verbose', '--print-certs', args.out])
    run([args.build_tools / 'zipalign', '-c', '-P', '16', '4', args.out])
    preserved = []
    with zipfile.ZipFile(args.input) as old, zipfile.ZipFile(args.out) as new:
        assert new.testzip() is None
        assert len(new.namelist()) == len(set(new.namelist()))
        for name in old.namelist():
            if name == LIB_PATH or name.startswith('META-INF/'):
                continue
            assert old.read(name) == new.read(name), name
            preserved.append(name)
        assert new.read(LIB_PATH) == patched
        assert set(new.namelist()) - set(old.namelist()) - {'assets/ZETTABRIDGE-GUEST4.txt'} <= \
               {n for n in new.namelist() if n.startswith('META-INF/')}
    details.update(input_apk_sha256=INPUT_SHA, apk_sha256=sha(args.out.read_bytes()),
                   preserved_zip_members=len(preserved), all_dex_unchanged=True,
                   manifest_unchanged=True, size_ratio_to_previous=0.9,
                   android_device_tested=False)
    args.out.with_suffix('.build.json').write_text(json.dumps(details, indent=2) + '\n')
    print(json.dumps(details, indent=2))


if __name__ == '__main__':
    main()
