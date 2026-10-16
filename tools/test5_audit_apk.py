#!/usr/bin/env python3
"""Read-only APK/AXML/DEX/ELF inventory. Python 3.10+, standard library only.

This is an inspection tool, not a binary translator or APK patcher. It does not
execute APK code. The XML output preserves typed values, not resolved resources.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path, PurePosixPath
import struct
import xml.etree.ElementTree as ET
import zipfile
import zlib

ANDROID = 'http://schemas.android.com/apk/res/android'
ET.register_namespace('android', ANDROID)


def uleb(data, off):
    value = 0
    for shift in range(0, 35, 7):
        b = data[off]
        off += 1
        value |= (b & 127) << shift
        if b < 128:
            return value, off
    raise ValueError('invalid ULEB128')


def cstring(data, off):
    return data[off:data.index(b'\0', off)].decode('utf-8', 'replace')


def parse_axml(data):
    if data[:4] != b'\x03\x00\x08\x00':
        raise ValueError('not binary Android XML')
    strings, stack, root = [], [], None
    off = 8
    def get(i):
        return None if i == 0xffffffff else strings[i]
    while off < len(data):
        kind, header, size = struct.unpack_from('<HHI', data, off)
        if size < header or size == 0 or off + size > len(data):
            raise ValueError('invalid AXML chunk')
        if kind == 1:
            count, _, flags, start, _ = struct.unpack_from('<5I', data, off + 8)
            def read_length(pos, utf8):
                if utf8:
                    v = data[pos]
                    return (((v & 127) << 8) | data[pos + 1], pos + 2) if v & 128 else (v, pos + 1)
                v, = struct.unpack_from('<H', data, pos)
                return (((v & 32767) << 16) | struct.unpack_from('<H', data, pos + 2)[0], pos + 4) if v & 32768 else (v, pos + 2)
            for i in range(count):
                rel, = struct.unpack_from('<I', data, off + header + 4 * i)
                pos = off + start + rel
                _, pos = read_length(pos, bool(flags & 256))
                if flags & 256:
                    length, pos = read_length(pos, True)
                    strings.append(data[pos:pos+length].decode('utf-8', 'replace'))
                else:
                    length, _ = read_length(off + start + rel, False)
                    strings.append(data[pos:pos+2*length].decode('utf-16le', 'replace'))
        elif kind == 0x102:
            ns, name, attr_start, attr_size, count = struct.unpack_from('<IIHHH', data, off + 16)
            tag = ('{' + get(ns) + '}' if get(ns) else '') + get(name)
            element = ET.Element(tag)
            for i in range(count):
                pos = off + 16 + attr_start + attr_size * i
                ans, aname, raw, _, _, typ, val = struct.unpack_from('<IIIHBBI', data, pos)
                key = ('{' + get(ans) + '}' if get(ans) else '') + get(aname)
                if raw != 0xffffffff:
                    value = get(raw)
                elif typ == 3:
                    value = get(val)
                elif typ == 0x12:
                    value = 'true' if val else 'false'
                elif typ == 0x10:
                    value = str(val if val < 0x80000000 else val - 0x100000000)
                elif typ == 1:
                    value = f'@0x{val:08x}'
                elif typ == 2:
                    value = f'?0x{val:08x}'
                else:
                    value = f'0x{val:08x}'
                element.set(key, value)
            if stack:
                stack[-1].append(element)
            else:
                root = element
            stack.append(element)
        elif kind == 0x103:
            stack.pop()
        off += size
    if stack or root is None:
        raise ValueError('unbalanced AXML')
    return root


def parse_elf(data):
    if data[:4] != b'\x7fELF' or data[5] != 1:
        raise ValueError('expected little-endian ELF')
    bits = {1: 32, 2: 64}[data[4]]
    h = struct.unpack_from('<HHIIIIIHHHHHH' if bits == 32 else '<HHIQQQIHHHHHH', data, 16)
    sections = [struct.unpack_from('<10I' if bits == 32 else '<IIQQQQIIQQ', data, h[5] + h[10] * i) for i in range(h[11])]
    def body(s):
        return data[s[4]:s[4] + s[5]]
    shstr = body(sections[h[12]])
    names = [cstring(shstr, s[0]) for s in sections]
    needed, symbols, tags, relocations = [], [], [], {}
    for s in sections:
        if s[1] == 6:
            st = body(sections[s[6]])
            for off in range(s[4], s[4] + s[5], s[9]):
                tag, val = struct.unpack_from('<iI' if bits == 32 else '<qQ', data, off)
                tags.append(tag)
                if tag == 1:
                    needed.append(cstring(st, val))
        elif s[1] == 11:
            st = body(sections[s[6]])
            for off in range(s[4], s[4] + s[5], s[9]):
                if bits == 32:
                    name, value, size, info, other, shndx = struct.unpack_from('<IIIBBH', data, off)
                else:
                    name, info, other, shndx, value, size = struct.unpack_from('<IBBHQQ', data, off)
                if name:
                    symbols.append({'name': cstring(st, name), 'defined': shndx != 0,
                                    'binding': info >> 4, 'type': info & 15,
                                    'value': value, 'size': size})
        elif s[1] in (4, 9):
            for off in range(s[4], s[4] + s[5], s[9]):
                info = struct.unpack_from('<I' if bits == 32 else '<Q', data, off + bits // 8)[0]
                typ = info & (255 if bits == 32 else 0xffffffff)
                relocations[str(typ)] = relocations.get(str(typ), 0) + 1
    segments = []
    for i in range(h[9]):
        p = struct.unpack_from('<8I' if bits == 32 else '<II6Q', data, h[4] + h[8] * i)
        if p[0] == 1:
            segments.append({'offset': p[1] if bits == 32 else p[2],
                             'vaddr': p[2] if bits == 32 else p[3], 'alignment': p[7]})
    return {'bits': bits, 'machine': h[1], 'elf_type': h[0], 'elf_flags': h[6],
            'needed': needed, 'sections': names, 'symbols': symbols,
            'load_segments': segments, 'relocation_types': relocations,
            'textrel_tag': 22 in tags,
            'bitcode_sections': [n for n in names if 'llvm' in n.lower() or 'bitcode' in n.lower()],
            'debug_sections': [n for n in names if n.startswith('.debug') or n == '.symtab']}


def opcode_width(units, pc):
    u, op = units[pc], units[pc] & 255
    if op == 0:
        if u == 0x100:
            return 4 + 2 * units[pc+1]
        if u == 0x200:
            return 2 + 4 * units[pc+1]
        if u == 0x300:
            count = units[pc+2] | (units[pc+3] << 16)
            return 4 + (units[pc+1] * count + 1) // 2
        return 1
    if op in (0x18,):
        return 5
    if op in (0xfa, 0xfb):
        return 4
    if op in (0x03, 0x06, 0x09, 0x14, 0x17, 0x1b, 0x24, 0x25, 0x26, 0x2a, 0x2b, 0x2c, 0xfc, 0xfd) or 0x6e <= op <= 0x72 or 0x74 <= op <= 0x78:
        return 3
    if op in (0x02, 0x05, 0x08, 0x13, 0x15, 0x16, 0x19, 0x1a, 0x1c, 0x1f, 0x20, 0x22, 0x23, 0x29, 0xfe, 0xff) or 0x2d <= op <= 0x3d or 0x44 <= op <= 0x6d or 0x90 <= op <= 0xaf or 0xd0 <= op <= 0xe2:
        return 2
    if op <= 0xe2:
        return 1
    raise ValueError(f'unsupported DEX opcode {op:02x}')


def parse_dex(data, filename):
    if data[:4] != b'dex\n' or len(data) < 112:
        raise ValueError('not DEX')
    if struct.unpack_from('<I', data, 40)[0] != 0x12345678:
        raise ValueError('unsupported DEX byte order')
    sc, so, tc, to, pc, po, fc, fo, mc, mo, cc, co = struct.unpack_from('<12I', data, 56)
    strings = []
    for i in range(sc):
        off, = struct.unpack_from('<I', data, so + 4 * i)
        _, pos = uleb(data, off)
        strings.append(cstring(data, pos))
    types = [strings[struct.unpack_from('<I', data, to + 4 * i)[0]] for i in range(tc)]
    protos = []
    for i in range(pc):
        _, ret, args = struct.unpack_from('<III', data, po + 12 * i)
        params = []
        if args:
            count, = struct.unpack_from('<I', data, args)
            params = [types[v] for v in struct.unpack_from('<' + 'H' * count, data, args+4)]
        protos.append('(' + ''.join(params) + ')' + types[ret])
    methods = []
    for i in range(mc):
        cls, proto, name = struct.unpack_from('<HHI', data, mo + 8*i)
        methods.append(types[cls] + '->' + strings[name] + protos[proto])
    fields = []
    for i in range(fc):
        cls, typ, name = struct.unpack_from('<HHI', data, fo+8*i)
        fields.append(types[cls] + '->' + strings[name] + ':' + types[typ])
    classes, declared, native, refs = {}, [], [], []
    for i in range(cc):
        cls, flags, sup, interfaces, source, annotations, class_data, static = struct.unpack_from('<8I', data, co+32*i)
        owner = types[cls]
        classes[owner] = types[sup] if sup != 0xffffffff else None
        if not class_data:
            continue
        pos, counts = class_data, []
        for _ in range(4):
            count, pos = uleb(data, pos)
            counts.append(count)
        for count in counts[:2]:
            idx = 0
            for _ in range(count):
                diff, pos = uleb(data, pos)
                access, pos = uleb(data, pos)
                idx += diff
        for count in counts[2:]:
            idx = 0
            for _ in range(count):
                diff, pos = uleb(data, pos)
                access, pos = uleb(data, pos)
                code, pos = uleb(data, pos)
                idx += diff
                method = methods[idx]
                record = {'dex': filename, 'method': method, 'access_flags': access, 'code_offset': code}
                declared.append(record)
                if access & 0x100:
                    native.append(record)
                if not code or not owner.startswith(('Lcom/apportable/', 'Lcom/noodlecake/')):
                    continue
                length, = struct.unpack_from('<I', data, code+12)
                units = struct.unpack_from('<' + 'H'*length, data, code+16)
                ins, ip = [], 0
                while ip < len(units):
                    op = units[ip] & 255
                    item = {'pc_code_units': ip, 'opcode': f'0x{op:02x}'}
                    if op in (0x1a, 0x1b):
                        index = units[ip+1] | ((units[ip+2] << 16) if op == 0x1b else 0)
                        item['string'] = strings[index]
                    elif 0x6e <= op <= 0x72 or 0x74 <= op <= 0x78:
                        item['invoke'] = methods[units[ip+1]]
                    elif 0x52 <= op <= 0x6d:
                        item['field'] = fields[units[ip+1]]
                    if len(item) > 2:
                        ins.append(item)
                    ip += opcode_width(units, ip)
                if ip != len(units):
                    raise ValueError('DEX instruction size mismatch: ' + method)
                refs.append({'dex': filename, 'method': method, 'code_offset': code, 'references': ins})
    return {'file': filename, 'version': data[4:7].decode(), 'size': len(data),
            'sha1_ok': hashlib.sha1(data[32:]).digest() == data[12:32],
            'adler32_ok': zlib.adler32(data[12:]) == struct.unpack_from('<I', data, 8)[0],
            'class_count': cc, 'declared_method_count': len(declared),
            'classes': classes, 'native_methods': native, 'references': refs}


def write_json(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('apk', type=Path)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    if args.apk.resolve().is_relative_to(args.out.resolve()):
        raise ValueError('put the output in a directory separate from the input APK')
    with zipfile.ZipFile(args.apk) as z:
        duplicate_names = len(z.namelist()) != len(set(z.namelist()))
        if duplicate_names:
            raise ValueError('duplicate ZIP names')
        manifest = parse_axml(z.read('AndroidManifest.xml'))
        ET.indent(manifest)
        ET.ElementTree(manifest).write(args.out/'AndroidManifest.decoded.xml', encoding='utf-8', xml_declaration=True)
        libs, dexes = [], []
        entries = []
        for info in z.infolist():
            entries.append({'name': info.filename, 'size': info.file_size, 'compressed_size': info.compress_size})
            if info.filename.startswith('lib/') and info.filename.endswith('.so'):
                data = z.read(info)
                lib = parse_elf(data)
                lib.update(path=info.filename, size=len(data), sha256=hashlib.sha256(data).hexdigest())
                libs.append(lib)
            elif info.filename.endswith('.dex'):
                dexes.append(parse_dex(z.read(info), info.filename))
        write_json(args.out/'apk_entries.json', entries)
    package = manifest.get('package')
    app = manifest.find('application')
    sdk = manifest.find('uses-sdk')
    launchers = []
    for activity in list(app.findall('activity')) + list(app.findall('activity-alias')):
        for intent in activity.findall('intent-filter'):
            actions = [a.get('{'+ANDROID+'}name') for a in intent.findall('action')]
            categories = [a.get('{'+ANDROID+'}name') for a in intent.findall('category')]
            if 'android.intent.action.MAIN' in actions and 'android.intent.category.LAUNCHER' in categories:
                launchers.append(activity.get('{'+ANDROID+'}targetActivity') or activity.get('{'+ANDROID+'}name'))
    classes = {k:v for d in dexes for k,v in d['classes'].items()}
    chains = []
    for name in launchers:
        if name.startswith('.'):
            name = package + name
        elif '.' not in name:
            name = package + '.' + name
        desc, chain = 'L' + name.replace('.', '/') + ';', []
        while desc and desc not in chain:
            chain.append(desc)
            desc = classes.get(desc)
        chains.append(chain)
    native = [m for d in dexes for m in d['native_methods']]
    apprefs = [r for d in dexes for r in d['references']]
    boot = [r for r in apprefs if any('loadLibrary(' in i.get('invoke', '') or 'System;->load(' in i.get('invoke', '') or 'nativeRun(' in i.get('invoke', '') or 'loadLibraries(' in i.get('invoke', '') for i in r['references'])]
    gpg = [r for r in apprefs if 'game' in r['method'].lower() and any(k in r['method'].lower() for k in ['google', 'play', 'signin', 'gpg'])]
    libnames = {PurePosixPath(l['path']).name for l in libs}
    external = sorted({n for l in libs for n in l['needed'] if n not in libnames})
    source_exts = {'.c','.cc','.cpp','.cxx','.m','.mm','.h','.hpp','.java','.kt','.bc','.ll','.a','.o','.gradle'}
    summary = {'apk_name': args.apk.name, 'apk_size': args.apk.stat().st_size,
               'apk_sha256': hashlib.sha256(args.apk.read_bytes()).hexdigest(),
               'manifest': {'package': package, 'version_name': manifest.get('{'+ANDROID+'}versionName'),
                            'version_code': manifest.get('{'+ANDROID+'}versionCode'),
                            'min_sdk': sdk.get('{'+ANDROID+'}minSdkVersion'),
                            'target_sdk': sdk.get('{'+ANDROID+'}targetSdkVersion'),
                            'application_class': app.get('{'+ANDROID+'}name'),
                            'launcher_chains': chains},
               'abis': sorted({l['path'].split('/')[1] for l in libs}),
               'native_library_count': len(libs), 'native_bytes': sum(l['size'] for l in libs),
               'elf_machine_counts': {str(m): sum(l['machine']==m for l in libs) for m in sorted({l['machine'] for l in libs})},
               'external_needed': external,
               'jni_export_count': sum(s['defined'] and s['name'].startswith('Java_') for l in libs for s in l['symbols']),
               'native_method_declaration_count': len(native),
               'source_like_entries': [i['name'] for i in entries if PurePosixPath(i['name']).suffix.lower() in source_exts],
               'bitcode_sections': {l['path']:l['bitcode_sections'] for l in libs if l['bitcode_sections']},
               'debug_sections': {l['path']:l['debug_sections'] for l in libs if l['debug_sections']},
               'dex': [{k:v for k,v in d.items() if k not in ('classes','native_methods','references')} for d in dexes]}
    write_json(args.out/'summary.json', summary)
    write_json(args.out/'native_inventory.json', [{k:v for k,v in l.items() if k != 'symbols'} for l in libs])
    write_json(args.out/'bootstrap_references.json', boot)
    write_json(args.out/'game_services_references.json', gpg)
    write_json(args.out/'apportable_noodlecake_references.json', apprefs)
    with (args.out/'native_methods.tsv').open('w',encoding='utf-8',newline='') as f:
        writer = csv.writer(f, delimiter='\t')
        writer.writerow(['dex','method','access_flags','code_offset'])
        writer.writerows([[m[k] for k in ('dex','method','access_flags','code_offset')] for m in native])
    with (args.out/'native_symbols.tsv').open('w',encoding='utf-8',newline='') as f:
        writer = csv.writer(f, delimiter='\t')
        writer.writerow(['library','name','defined','binding','type','value','size'])
        for lib in libs:
            writer.writerows([[PurePosixPath(lib['path']).name] + [s[k] for k in ('name','defined','binding','type','value','size')] for s in lib['symbols']])
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
