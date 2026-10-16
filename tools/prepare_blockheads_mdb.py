#!/usr/bin/env python3
"""Prepare a local LMDB-only fixture, never an installable patched game APK."""
import argparse
import hashlib
from pathlib import Path
import struct
import zipfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game', type=Path, required=True, help='Original user-supplied Blockheads 1.7.6 APK/ZIP')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    assert hashlib.sha256(args.game.read_bytes()).hexdigest() == (
        'cae0371354dfda125793ba974c1f7a55b2161ed6d9c458f962da9eb468f8ec54')
    args.out.mkdir(parents=True, exist_ok=True)
    count = 0
    with zipfile.ZipFile(args.game) as archive:
        for name in archive.namelist():
            if not name.startswith('lib/armeabi-v7a/') or not name.endswith('.so'):
                continue
            data = bytearray(archive.read(name))
            assert data[:6] == b'\x7fELF\x01\x01'
            # ART is absent in this test. Disable ELF constructor entry points
            # in copies only. libv and every function instruction stay intact.
            if Path(name).name != 'libv.so':
                phoff = struct.unpack_from('<I', data, 28)[0]
                phsize, phnum = struct.unpack_from('<HH', data, 42)
                for i in range(phnum):
                    ph = struct.unpack_from('<8I', data, phoff + i * phsize)
                    if ph[0] != 2:
                        continue
                    for offset in range(ph[1], ph[1] + ph[4], 8):
                        tag = struct.unpack_from('<I', data, offset)[0]
                        if tag in (12, 27):  # DT_INIT, DT_INIT_ARRAYSZ
                            struct.pack_into('<I', data, offset + 4, 0)
            (args.out / Path(name).name).write_bytes(data)
            count += 1
    assert count == 25
    print('Prepared 25 local fixture libraries; no APK was created.')


if __name__ == '__main__':
    main()
