#!/usr/bin/env python3
"""Execute Guest4 and the original native-mode method with modeled OS/ObjC calls.

Requires pyelftools and Unicorn 2.1.4. This is ARM instruction validation,
not an Android display, touch, lifecycle, or image-quality test.
"""
import argparse
import io
import json
import math
from pathlib import Path
import struct
import zipfile

from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn import arm_const as ar

from build_blockheads_ui import LIB_PATH, LIB_SHA, HOOK, CONTINUATION, patch_library, sha

STACK = 0x25000000
EXTERNAL = 0x30000000
STOP = EXTERNAL + 0xffffc


def f32(value):
    return struct.unpack('<f', struct.pack('<f', value))[0]


def bits(value):
    return struct.unpack('<I', struct.pack('<f', value))[0]


def from_bits(value):
    return struct.unpack('<f', struct.pack('<I', value))[0]


def load(raw, base):
    elf = ELFFile(io.BytesIO(raw))
    u = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    u.mem_map(base, 0x1100000)
    u.mem_map(STACK, 0x200000)
    u.mem_map(EXTERNAL, 0x100000)
    for seg in elf.iter_segments():
        if seg['p_type'] == 'PT_LOAD':
            u.mem_write(base + seg['p_vaddr'], seg.data())
    imports = {}
    syms = elf.get_section_by_name('.dynsym')
    next_fn = EXTERNAL
    for name in ('.rel.dyn', '.rel.plt'):
        for rel in elf.get_section_by_name(name).iter_relocations():
            address = base + rel['r_offset']
            kind = rel['r_info_type']
            symbol = syms.get_symbol(rel['r_info_sym']) if rel['r_info_sym'] else None
            old = struct.unpack('<I', u.mem_read(address, 4))[0]
            if kind == 23:  # R_ARM_RELATIVE
                value = old + base
            elif symbol and kind in (2, 21, 22):
                if symbol['st_shndx'] == 'SHN_UNDEF':
                    value = next_fn
                    imports[value] = symbol.name
                    next_fn += 4
                else:
                    value = base + symbol['st_value']
                if kind == 2:  # R_ARM_ABS32
                    value += old
            else:
                continue
            u.mem_write(address, struct.pack('<I', value & 0xffffffff))
    u.reg_write(ar.UC_ARM_REG_C1_C0_2, 0x00f00000)
    u.reg_write(ar.UC_ARM_REG_FPEXC, 0x40000000)
    return u, imports


def mode_case(raw, base, width, points):
    u, imports = load(raw, base)
    # Test12 writes this literal before guest startup; leave its native path intact.
    u.mem_write(base + 0x26d904, struct.pack('<f', points))
    calls = []
    scale = []
    instance = STACK + 0x10000

    def finish(value):
        u.reg_write(ar.UC_ARM_REG_R0, value)
        u.reg_write(ar.UC_ARM_REG_PC, u.reg_read(ar.UC_ARM_REG_LR))

    def hook(uc, address, size, unused):
        if address == base + 0x491004:
            calls.append('nativeWidth')
            finish(width)
        elif address in imports:
            name = imports[address]
            if name in ('printf', 'NSLog'):
                calls.append(name)
                finish(0)
            elif name == 'objc_msgSend':
                selector = bytes(u.mem_read(u.reg_read(ar.UC_ARM_REG_R1), 128)).split(b'\0')[0].decode()
                calls.append(selector)
                assert selector in ('alloc', 'initWithScale:', 'autorelease'), selector
                if selector == 'initWithScale:':
                    scale.append(from_bits(u.reg_read(ar.UC_ARM_REG_R2)))
                finish(instance)
            else:
                raise AssertionError(('unexpected import', name))

    u.hook_add(UC_HOOK_CODE, hook)
    initial_sp = STACK + 0x1f0000
    u.reg_write(ar.UC_ARM_REG_SP, initial_sp)
    u.reg_write(ar.UC_ARM_REG_LR, STOP)
    u.reg_write(ar.UC_ARM_REG_R0, instance)
    u.reg_write(ar.UC_ARM_REG_R1, 0)
    u.reg_write(ar.UC_ARM_REG_R2, 0)
    u.emu_start(base + 0x26d804, STOP, count=1000)
    assert u.reg_read(ar.UC_ARM_REG_PC) == STOP, 'nativeMode did not return'
    assert u.reg_read(ar.UC_ARM_REG_SP) == initial_sp
    assert u.reg_read(ar.UC_ARM_REG_R0) == instance
    assert len(scale) == 1 and calls[0] == 'nativeWidth', (scale, calls)
    return scale[0], calls


def continuation_case(patched, base, points):
    u, _ = load(patched, base)
    gpr = [getattr(ar, 'UC_ARM_REG_R%d' % i) for i in range(13)]
    fpregs = [getattr(ar, 'UC_ARM_REG_S%d' % i) for i in range(32)]
    for i, reg in enumerate(gpr):
        u.reg_write(reg, 0x1000 + i)
    for i, reg in enumerate(fpregs):
        u.reg_write(reg, bits(0.25 + i))
    u.reg_write(ar.UC_ARM_REG_FP, STACK + 0x10000)
    u.reg_write(ar.UC_ARM_REG_SP, STACK + 0x8000)
    u.reg_write(ar.UC_ARM_REG_LR, STOP)
    u.reg_write(ar.UC_ARM_REG_S0, bits(3.312))
    u.reg_write(ar.UC_ARM_REG_S2, bits(points))
    u.reg_write(ar.UC_ARM_REG_APSR, 0xa8000000)
    u.reg_write(ar.UC_ARM_REG_FPSCR, 0xa0000010)
    preserved = gpr + [ar.UC_ARM_REG_SP, ar.UC_ARM_REG_LR, ar.UC_ARM_REG_APSR,
                       ar.UC_ARM_REG_FPSCR] + fpregs[1:]
    before = [u.reg_read(reg) for reg in preserved]
    u.emu_start(base + HOOK, base + CONTINUATION, count=100)
    assert u.reg_read(ar.UC_ARM_REG_PC) == base + CONTINUATION
    after = [u.reg_read(reg) for reg in preserved]
    assert before == after, [(r, a, b) for r, a, b in zip(preserved, before, after) if a != b]
    wanted = f32(f32(3.312) * f32(0.9)) if 600 < f32(points) <= 682 else f32(3.312)
    assert u.reg_read(ar.UC_ARM_REG_S0) == bits(wanted)
    assert struct.unpack('<f', u.mem_read(STACK + 0x10000 - 24, 4))[0] == wanted


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--original', type=Path, required=True)
    p.add_argument('--apk', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    original = args.original.read_bytes()
    assert sha(original) == LIB_SHA
    authored, details = patch_library(original)
    with zipfile.ZipFile(args.apk) as apk:
        patched = apk.read(LIB_PATH)
    assert patched == authored, 'APK does not contain the authored patch'
    # Test12 native-screen and offline-crystal compatibility fingerprints.
    for start, size in ((0x9c5260, 4), (0x26d804, 4), (0x26d824, 4),
                        (0x26d85c, 4), (0x26d904, 4), (0xb60380, 0xe28),
                        (0xb5d19c, 4)):
        assert patched[start:start + size] == original[start:start + size]
    assert ELFFile(io.BytesIO(original)).get_section_by_name('.note.gnu.build-id').data() == \
           ELFFile(io.BytesIO(patched)).get_section_by_name('.note.gnu.build-id').data()
    results = []
    guard_cases = [600, 600.0001, 650, 600 / 0.88, 682, 683, 0, -1, float('inf'), float('nan')]
    for base in (0x10000000, 0x40000000):
        for width, points in ((1080, 600), (2256, 600 / 0.88), (2504, 600 / 0.88),
                              (1800, 650), (2256, 600), (2256, 682)):
            old, old_calls = mode_case(original, base, width, points)
            new, new_calls = mode_case(patched, base, width, points)
            factor = 0.9 if 600 < f32(points) <= 682 else 1
            assert new_calls == old_calls
            assert math.isclose(new, old * factor, rel_tol=2e-7), (new, old, factor)
            if factor < 1:
                assert not math.isclose(old, new, rel_tol=0.01), 'original must fail the smaller-size requirement'
            results.append(dict(base=hex(base), native_width=width, policy_points=points,
                                original_scale=old, guest4_scale=new, expected_ratio=factor))
        for points in guard_cases:
            continuation_case(patched, base, points)
    proof = dict(native_mode_cases=results, continuation_guard_and_abi_cases=2 * len(guard_cases),
                 actual_apk_code_executed=True, test12_patch_fingerprints_unchanged=True,
                 modeled_boundaries=['native display width', 'logging', 'Objective-C dispatch'],
                 android_device_tested=False, patched_library_sha256=details['patched_sha256'])
    args.out.write_text(json.dumps(proof, indent=2) + '\n')
    print('PASS: %d original/patched native-mode comparisons; %d ARM guard/ABI cases' %
          (len(results), 2 * len(guard_cases)))


if __name__ == '__main__':
    main()
