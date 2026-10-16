#!/usr/bin/env python3
"""Verify the Test9 -> Test10 APK's scoped changes; this does not execute Android."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import xml.etree.ElementTree as ET
import zipfile
import zlib

from test5_audit_apk import parse_axml, parse_dex, parse_elf
from verify_blockheads_test6 import method


def verify(base_path, apk_path, native_path, *,
           base_sha='89cb8da5046d953ecced711e5f068a93cf5a3ec1afe17bb0369da858d4f70208',
           base_report=b'zettabridge-diagnostic-report 9', revision=10, suffix='native-screen', direct_launch=False):
    assert hashlib.sha256(base_path.read_bytes()).hexdigest() == base_sha
    version_code = 20261009 + revision
    version_name = f'0.1.0-blockheads-test{revision}-{suffix}'
    report_header = f'zettabridge-diagnostic-report{revision}'.encode('ascii')
    assert len(base_report) == len(report_header)
    with zipfile.ZipFile(base_path) as base, zipfile.ZipFile(apk_path) as apk:
        assert len(apk.namelist()) == len(set(apk.namelist()))
        assert apk.testzip() is None
        allowed = {'AndroidManifest.xml', 'classes.dex', 'classes2.dex', 'lib/arm64-v8a/libzbridge.so'}
        if direct_launch:
            allowed.add('resources.arsc')
        preserved = []
        for name in base.namelist():
            if name.startswith('META-INF/') or name in allowed:
                continue
            assert base.read(name) == apk.read(name), name
            preserved.append(name)
        added = set(apk.namelist()) - set(base.namelist())
        resources = {n for n in added if n.startswith('res/')} if direct_launch else set()
        assert {n for n in added if not n.startswith('META-INF/')} == resources | {f'assets/licenses/TEST{revision}-NOTICE.txt'}
        if direct_launch:
            expected_resources = {'res/drawable/' + n + '.xml' for n in
                                  ('ic_background', 'ic_foreground', 'ic_monochrome', 'ic_manage')}
            expected_resources |= {'res/mipmap-anydpi-v26/ic_launcher.xml',
                                   'res/mipmap-anydpi-v33/ic_launcher.xml', 'res/xml/shortcuts.xml'}
            assert resources == expected_resources, resources
            # Parse each compiled resource too: a manifest-only icon/shortcut
            # declaration is not sufficient for an installable launcher.
            compiled_resources = {n: parse_axml(apk.read(n)) for n in resources}
            assert all(compiled_resources[n].tag == 'vector' for n in resources if '/drawable/' in n)
            for version in (26, 33):
                icon = compiled_resources[f'res/mipmap-anydpi-v{version}/ic_launcher.xml']
                assert icon.tag == 'adaptive-icon'
                assert [c.tag for c in icon] == ['background', 'foreground'] + (['monochrome'] if version == 33 else [])
        before, after = base.read('classes.dex'), apk.read('classes.dex')
        assert before.count(base_report) == 1
        expected = bytearray(before.replace(base_report, report_header))
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
        entry_class = 'Lcom/zettabridge/launcher/BlockheadsLaunchActivity;'
        assert all('Test8Application' in name or (direct_launch and name == entry_class) for name in classes)
        if direct_launch:
            assert classes[entry_class] == 'Landroid/app/Activity;'
            # Compile-only placeholders must never shadow the working base DEX.
            assert not (set(dex[0]['classes']) & set(classes))
            required_methods = {
                'Lcom/zettabridge/launcher/PluginStore;->find(Landroid/content/Context;Ljava/lang/String;)Lcom/zettabridge/launcher/PluginRecord;',
                'Lcom/zettabridge/launcher/PluginRecord;->isLaunchable()Z',
                'Lcom/zettabridge/launcher/PluginRecord;->apk()Ljava/io/File;',
                'Lcom/zettabridge/launcher/PluginSwitchActivity;->intent(Landroid/content/Context;Ljava/lang/String;)Landroid/content/Intent;',
            }
            methods = {method(before, i) for i in range(struct.unpack_from('<I', before, 88)[0])}
            assert required_methods <= methods, 'base DEX routing ABI changed'
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
        assert manifest.get(ns + 'versionCode') == str(version_code)
        assert manifest.get(ns + 'versionName') == version_name
        assert old_manifest.find('uses-sdk').attrib == manifest.find('uses-sdk').attrib
        assert manifest.find('application').get(ns + 'name') == 'com.zettabridge.launcher.Test8Application'
        app_label = 'Blockheads - ZettaBridge' if direct_launch else f'ZettaBridge Blockheads Test {revision}'
        assert manifest.find('application').get(ns + 'label') == app_label
        assert [n.attrib for n in old_manifest.findall('uses-permission')] == [n.attrib for n in manifest.findall('uses-permission')]
        # Apart from build identity, keep every activity/provider/service and
        # application setting from the working Test9 wrapper.
        old_manifest.set(ns + 'versionCode', str(version_code))
        old_manifest.set(ns + 'versionName', version_name)
        old_app, new_app = old_manifest.find('application'), manifest.find('application')
        old_app.set(ns + 'label', app_label)
        if direct_launch:
            icon = new_app.get(ns + 'icon')
            assert icon.startswith('@0x7f') and new_app.get(ns + 'roundIcon') == icon
            old_app.set(ns + 'icon', icon)
            old_app.set(ns + 'roundIcon', icon)
            library = next(a for a in old_app.findall('activity') if a.get(ns + 'name') == 'com.zettabridge.launcher.LibraryActivity')
            library.remove(library.find('intent-filter'))
            library.set(ns + 'label', 'ZettaBridge Settings')
            entry = next(a for a in new_app.findall('activity') if a.get(ns + 'name') == 'com.zettabridge.launcher.BlockheadsLaunchActivity')
            assert entry.attrib == {
                ns + 'name': 'com.zettabridge.launcher.BlockheadsLaunchActivity',
                ns + 'exported': 'true', ns + 'theme': '@0x01030055',
                ns + 'taskAffinity': 'com.zettabridge.blockheadstest5.entry', ns + 'excludeFromRecents': 'true',
            }
            expected = ET.Element('activity', entry.attrib)
            intent_filter = ET.SubElement(expected, 'intent-filter')
            ET.SubElement(intent_filter, 'action', {ns + 'name': 'android.intent.action.MAIN'})
            ET.SubElement(intent_filter, 'category', {ns + 'name': 'android.intent.category.LAUNCHER'})
            shortcut_id = entry.find('meta-data').get(ns + 'resource')
            assert shortcut_id.startswith('@0x7f')
            ET.SubElement(expected, 'meta-data', {ns + 'name': 'android.app.shortcuts', ns + 'resource': shortcut_id})
            old_app.append(expected)
            shortcuts = compiled_resources['res/xml/shortcuts.xml']
            assert shortcuts.tag == 'shortcuts' and len(shortcuts) == 1
            shortcut = shortcuts[0]
            assert shortcut.get(ns + 'shortcutId') == 'manage' and shortcut.get(ns + 'enabled') == 'true'
            assert len(shortcut) == 1 and shortcut[0].attrib == {
                ns + 'action': 'android.intent.action.VIEW',
                ns + 'targetPackage': 'com.zettabridge.blockheadstest5',
                ns + 'targetClass': 'com.zettabridge.launcher.LibraryActivity',
            }
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
            'addon_scope': 'recompiled addon: configuration dispatch retained, tracing disabled, native mode opted in; launch density policy',
            'package': manifest.get('package'),
            'version_code': version_code,
            'direct_launch_with_import_fallback': direct_launch,
            'adaptive_icon_and_settings_shortcut': direct_launch,
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
