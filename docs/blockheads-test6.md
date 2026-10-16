# Blockheads Test6: canonical APK bundle path

Test6 fixes the APK path published in ApplicationInfo. It updates Test5 in place
and retains its native engine and runtime assets byte-for-byte. It is still an
ARM32 game running through translation, not a completed native ARM64 port.

## Device evidence and reproduction

The user's Test5 run (2026-10-11 10:30 KST, Android API 37) repeatedly sampled
libSystem.so + 0x2cde8, returning to libCoreFoundation.so + 0x88834. Disassembly
identifies the exclusive-store retry loop in OSSpinLockLock, called from
CFBundleGetInfoDictionary. The repeated r2 value is 0x5c, matching the lock field
offset from a NULL bundle. The loader remained inside libFoundation dlopen;
recent JNI calls stayed at 246. This is not evidence of a repeating JNI call.

A local fixture used the original supplied Blockheads 1.7.6 libraries, the Test5
ARM32 sysroot, and the Android ARM64 zbcore/Dynarmic object files used to build
Test5. A statically linked Android ARM64 zbrun ran under qemu-aarch64-static on
the x86_64 development host. QEMU was only a development test tool and is not
included in, linked into, or required by the APK.

The fixture sets targetSdk 27, calls libv_init, and loads the libraries in their
observed order with RTLD_NOW. It does not provide ART/JNI, UI, graphics, or a
gameplay test. libv redirects stderr, so the fixture duplicates the diagnostic
descriptor before calling it.

Results:

- The original OSSpinLockLock instructions acquired an uncontended valid lock
  under both x86_64 and ARM64 translation. The isolated unmapped-pointer case
  faulted. There is no evidence for replacing the translator's atomic machinery.
- A direct CFBundleGetInfoDictionary(NULL) call in the loaded game libraries
  reproduced the same 0x2cde8 / 0x88834 / r2=0x5c loop.
- Publishing an APK through a symlinked parent directory reproduced the actual
  Foundation-load stall, including r3=0xfffd0afc. The run was stopped at 35 seconds.
- Publishing the canonical path to the very same APK completed Foundation
  dlopen. No game-library instruction or lock was bypassed.
- Using the launcher package name as the executable suffix alone did not
  reproduce the stall; the fix does not change package/UID identity.

The device's Java paths use /data/user/0 while native canonical paths use
/data/data. This matches the reproduced alias condition. Device confirmation is
still needed; no claim is made that all subsequent game startup stages work.

## Minimal change

PluginStore.applicationInfo now uses File.getCanonicalPath() for sourceDir and
copies that same value into publicSourceDir. PluginContext and PackageManagerHook
already publish these fields. Thus Apportable's PACKAGE_CODE_PATH,
PACKAGE_RESOURCE_PATH, and CFProcessPath share the resolved APK prefix before
libv/CoreFoundation initialize their cached bundle paths.

The source method declares IOException; its two callers already propagate it.
No cache deletion, APK reimport, storage migration, or guest APK modification is
required. Native/data directory semantics and host package identity are unchanged.

The shipped APK is a scoped edit of the pinned Test5 APK, whose full Test4 Java
source was not available. In its existing classes.dex, only the invoke operand
at 0xc872 changes from File.getPath (method 0x248) to File.getCanonicalPath (0x245).
The preimage and input APK hash are asserted. The diagnostic report version and
DEX checksums also change. The additional DEX renames Test5Application to
Test6Application, preserving its tracing and stack-sampling behavior.

Input Test5 SHA-256:
`c618ccf9bc24a3901976ac798c8e279194754f5d52a4a35ac69dc6dca27a68d1`.

## Validation

- Symlinked APK / canonical APK native bootstrap comparison: reproduced / passed.
- Launcher Java sources compile with JDK 17 and SDK 35. The existing external
  HiddenApiBypass signature was supplied as a compile-only stub, never packaged.
- Primary DEX is exactly the allowed operand, report-version, and checksum edit.
- All 36 existing assets and the native library match Test5 byte-for-byte.
- New DEX class set and checksums, same application ID, higher versionCode, and
  unchanged SDK/permission declarations: passed.
- APK v2 signature, Test5 signer identity, and 16 KiB ZIP alignment: passed.
- Android device startup and gameplay: not tested here.

## Build and use

Package remains com.zettabridge.blockheadstest5. VersionCode is 20261015 and the
label is ZettaBridge Blockheads Test 6. Install over Test5, open the existing
Blockheads entry once, wait at least 50 seconds, and obtain the new run report.
Keep app data. Inspect the new PackageManager paths and whether Foundation has
joined proxy-loaded; the total need not be 11 if later libraries also succeed.

Use tools/build_blockheads_test6.py with the pinned Test5 input APK, JDK 17,
SDK platform/build-tools 35, tools/test5_audit_apk.py copied as audit_apk.py in
--audit-dir, and the matching experimental signing certificate/key. No native
rebuild is needed. A different signing key cannot update the user's installation.
The key is not distributed. Run tools/verify_blockheads_test6.py afterwards.

The install archive includes the pinned input, incremental and cumulative source
patches, fixture source, and before/after evidence. It contains no game assets,
game APK, emulator binaries, toolchains, or private keys.
