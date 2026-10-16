#!/usr/bin/env python3
"""Check the pinned Test5 -> Test6 APK's exact mutation scope (no device execution)."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import zipfile
import zlib

from test5_audit_apk import parse_axml, parse_dex, uleb, cstring


def method(data, index):
    so = struct.unpack_from('<I', data, 60)[0]
    to = struct.unpack_from('<I', data, 68)[0]
    po = struct.unpack_from('<I', data, 76)[0]
    mo = struct.unpack_from('<I', data, 92)[0]

    def string(i):
        off = struct.unpack_from('<I', data, so + 4 * i)[0]
        return cstring(data, uleb(data, off)[1])

    def typ(i):
        return string(struct.unpack_from('<I', data, to + 4 * i)[0])

    cls, proto, name = struct.unpack_from('<HHI', data, mo + 8 * index)
    _, ret, args = struct.unpack_from('<III', data, po + 12 * proto)
    assert args == 0
    return typ(cls) + '->' + string(name) + '()' + typ(ret)


def verify(base_path, apk_path):
    assert hashlib.sha256(base_path.read_bytes()).hexdigest() == (
        'c618ccf9bc24a3901976ac798c8e279194754f5d52a4a35ac69dc6dca27a68d1')
    with zipfile.ZipFile(base_path) as base, zipfile.ZipFile(apk_path) as apk:
        assert len(apk.namelist()) == len(set(apk.namelist()))
        assert apk.testzip() is None
        allowed = {'AndroidManifest.xml', 'classes.dex', 'classes2.dex'}
        preserved = []
        for name in base.namelist():
            if name.startswith('META-INF/') or name in allowed:
                continue
            assert base.read(name) == apk.read(name), name
            preserved.append(name)
        added = set(apk.namelist()) - set(base.namelist())
        assert {n for n in added if not n.startswith('META-INF/')} == {'assets/licenses/TEST6-NOTICE.txt'}
        before, after = base.read('classes.dex'), apk.read('classes.dex')
        assert method(after, 0x248) == 'Ljava/io/File;->getPath()Ljava/lang/String;'
        assert method(after, 0x245) == 'Ljava/io/File;->getCanonicalPath()Ljava/lang/String;'
        expected = bytearray(before.replace(b'zettabridge-diagnostic-report 5', b'zettabridge-diagnostic-report 6'))
        assert expected[0xc870:0xc87c] == bytes.fromhex('6e10480200000c005b100e00')
        expected[0xc872:0xc874] = bytes.fromhex('4502')
        expected[12:32] = hashlib.sha1(expected[32:]).digest()
        struct.pack_into('<I', expected, 8, zlib.adler32(expected[12:]) & 0xffffffff)
        assert after == expected, 'unexpected primary DEX change'
        dex = [parse_dex(apk.read(n), n) for n in ('classes.dex', 'classes2.dex')]
        assert all(d['sha1_ok'] and d['adler32_ok'] for d in dex)
        classes = dex[1]['classes']
        assert len(classes) == 3
        assert classes['Lcom/zettabridge/launcher/Test6Application;'] == 'Lcom/zettabridge/launcher/ZbApplication;'
        assert all('Test6Application' in name for name in classes)
        ns = '{http://schemas.android.com/apk/res/android}'
        old_manifest, manifest = (parse_axml(z.read('AndroidManifest.xml')) for z in (base, apk))
        assert manifest.get('package') == old_manifest.get('package') == 'com.zettabridge.blockheadstest5'
        assert manifest.get(ns + 'versionCode') == '20261015'
        assert manifest.get(ns + 'versionName') == '0.1.0-blockheads-test6-canonical-apk'
        assert old_manifest.find('uses-sdk').attrib == manifest.find('uses-sdk').attrib
        assert manifest.find('application').get(ns + 'name') == 'com.zettabridge.launcher.Test6Application'
        assert [n.attrib for n in old_manifest.findall('uses-permission')] == [n.attrib for n in manifest.findall('uses-permission')]
        return {
            'apk_sha256': hashlib.sha256(apk_path.read_bytes()).hexdigest(),
            'checks_passed': True,
            'primary_dex_scope': 'one File.getPath -> getCanonicalPath operand, report version, checksums',
            'native_engine_byte_identical': True,
            'preserved_asset_count': sum(n.startswith('assets/') for n in preserved),
            'addon_classes': sorted(classes),
            'package': manifest.get('package'),
            'version_code': 20261015,
            'android_device_tested': False,
        }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('base', type=Path)
    parser.add_argument('apk', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.base, args.apk)
    args.out.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
