#!/usr/bin/env python3
"""Verify the Test9 -> Test10 APK's scoped changes; this does not execute Android."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import zipfile
import zlib

from test5_audit_apk import parse_axml, parse_dex, parse_elf
from verify_blockheads_test6 import method


def verify(base_path, apk_path, native_path):
    assert hashlib.sha256(base_path.read_bytes()).hexdigest() == (
        '89cb8da5046d953ecced711e5f068a93cf5a3ec1afe17bb0369da858d4f70208')
    with zipfile.ZipFile(base_path) as base, zipfile.ZipFile(apk_path) as apk:
        assert len(apk.namelist()) == len(set(apk.namelist()))
        assert apk.testzip() is None
        allowed = {'AndroidManifest.xml', 'classes.dex', 'classes2.dex', 'lib/arm64-v8a/libzbridge.so'}
        preserved = []
        for name in base.namelist():
            if name.startswith('META-INF/') or name in allowed:
                continue
            assert base.read(name) == apk.read(name), name
            preserved.append(name)
        added = set(apk.namelist()) - set(base.namelist())
        assert {n for n in added if not n.startswith('META-INF/')} == {'assets/licenses/TEST10-NOTICE.txt'}
        before, after = base.read('classes.dex'), apk.read('classes.dex')
        assert before.count(b'zettabridge-diagnostic-report 9') == 1
        expected = bytearray(before.replace(b'zettabridge-diagnostic-report 9', b'zettabridge-diagnostic-report10'))
        assert method(after, 0x245) == 'Ljava/io/File;->getCanonicalPath()Ljava/lang/String;'
        assert expected[0xc870:0xc87c] == bytes.fromhex('6e10450200000c005b100e00')
        expected[12:32] = hashlib.sha1(expected[32:]).digest()
        struct.pack_into('<I', expected, 8, zlib.adler32(expected[12:]) & 0xffffffff)
        assert after == expected, 'unexpected primary DEX change'
        dex = [parse_dex(apk.read(n), n) for n in ('classes.dex', 'classes2.dex')]
        assert all(d['sha1_ok'] and d['adler32_ok'] for d in dex)
        classes = dex[1]['classes']
        assert len(classes) >= 2
        assert classes['Lcom/zettabridge/launcher/Test8Application;'] == 'Lcom/zettabridge/launcher/ZbApplication;'
        assert all('Test8Application' in name for name in classes)
        native = apk.read('lib/arm64-v8a/libzbridge.so')
        assert native == native_path.read_bytes()
        assert native[:6] == b'\x7fELF\x02\x01'
        assert struct.unpack_from('<H', native, 18)[0] == 183
        phoff = struct.unpack_from('<Q', native, 32)[0]
        phsize, phnum = struct.unpack_from('<HH', native, 54)
        loads = [struct.unpack_from('<IIQQQQQQ', native, phoff + i * phsize)
                 for i in range(phnum) if struct.unpack_from('<I', native, phoff + i * phsize)[0] == 1]
        assert loads and all(p[7] >= 16384 and (p[2] - p[3]) % 16384 == 0 for p in loads)
        old_elf, elf = (parse_elf(data) for data in (base.read('lib/arm64-v8a/libzbridge.so'), native))
        assert sorted(old_elf['needed']) == sorted(elf['needed'])
        exported = lambda e: {s['name'] for s in e['symbols'] if s['defined'] and s['binding'] in (1, 2)}
        assert exported(old_elf) <= exported(elf), 'prior native exports lost'
        assert 'Java_com_zettabridge_launcher_Test8Application_inspectNative' in exported(elf)

        ns = '{http://schemas.android.com/apk/res/android}'
        old_manifest, manifest = (parse_axml(z.read('AndroidManifest.xml')) for z in (base, apk))
        assert manifest.get('package') == old_manifest.get('package') == 'com.zettabridge.blockheadstest5'
        assert manifest.get(ns + 'versionCode') == '20261019'
        assert manifest.get(ns + 'versionName') == '0.1.0-blockheads-test10-native-screen'
        assert old_manifest.find('uses-sdk').attrib == manifest.find('uses-sdk').attrib
        assert manifest.find('application').get(ns + 'name') == 'com.zettabridge.launcher.Test8Application'
        assert manifest.find('application').get(ns + 'label') == 'ZettaBridge Blockheads Test 10'
        assert [n.attrib for n in old_manifest.findall('uses-permission')] == [n.attrib for n in manifest.findall('uses-permission')]
        # Apart from build identity, keep every activity/provider/service and
        # application setting from the working Test9 wrapper.
        old_manifest.set(ns + 'versionCode', '20261019')
        old_manifest.set(ns + 'versionName', '0.1.0-blockheads-test10-native-screen')
        old_manifest.find('application').set(ns + 'label', 'ZettaBridge Blockheads Test 10')
        def tree(node):
            return node.tag, sorted(node.attrib.items()), [tree(child) for child in node]
        assert tree(old_manifest) == tree(manifest), 'unexpected manifest setting changed'
        return {
            'apk_sha256': hashlib.sha256(apk_path.read_bytes()).hexdigest(),
            'checks_passed': True,
            'primary_dex_scope': 'report version and checksums only; Test6 canonical-path fix preserved',
            'native_sha256': hashlib.sha256(native).hexdigest(),
            'native_matches_tested_build': True,
            'native_abi': 'arm64-v8a',
            'native_load_segments_16k_aligned': True,
            'native_needed_libraries': elf['needed'],
            'preserved_asset_count': sum(n.startswith('assets/') for n in preserved),
            'addon_classes': sorted(classes),
            'addon_scope': 'recompiled addon: configuration dispatch retained, tracing disabled, native mode opted in',
            'package': manifest.get('package'),
            'version_code': 20261019,
            'android_device_tested': False,
        }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('base', 'apk', 'native', 'out'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.base, args.apk, args.native)
    args.out.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
