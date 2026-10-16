# Blockheads Test5: native load tracing

This is a separate diagnostic launcher, not a completed native ARM64 port and not
a verified fix for the title-screen stall. The game remains an ARM32 guest.

## Input and evidence

- User supplied `v4.zip`: SHA-256
  `fa402717c190809b8209572db5e85f60033773a31c96acd9522a25c911d5cedd`.
- Its Test4 APK: SHA-256
  `c2e1a87b1a23467f6ac6b83bc6797728790305a0511f00e8ea268129f1f897a0`.
- Device reported Android SDK 37, 4096-byte pages. No device is connected here.
- The 2026-10-10 22:42 run loaded ten proxies and executed libv JNI_OnLoad plus
  init/setenv. It entered libFoundation.so loading without recording completion.
  There were no new Java exceptions, no reported unimplemented calls, and no GL
  calls. Older PendingIntent and SIGKILL entries belong to previous runs.
- Repeated recent-JNI names without a cumulative counter do not establish a loop.
  A stale syscall counter does not establish which code is currently running.

## Provenance and preservation

The supplied Test4 source patch is an incremental Java diagnostic patch, not the
complete source of the APK. Its earlier custom Java code and native adapters
cannot be recovered exactly as source from that patch.

The build therefore retains Test4 classes.dex verbatim except for the same-length
report-version string and DEX checksums. All 35 Test4 assets, including the proxy,
guest libraries and sysroot, are retained byte-for-byte. An additional DEX contains
only Test5Application and its generated lambda classes. It calls the original
ZbApplication.onCreate; compile-only stubs are never packaged.

The native core is rebuilt from ZailoxTT/ZettaBridge commit
`d6066b9b9e61de27041ba6e1f3c499c080c9e2b7`, with its two documented Dynarmic
patches, the diagnostic changes below, and reconstructed Android adapters for
AndroidBitmap_getInfo/lockPixels/unlockPixels and glFrustumf/glOrthof. These five
adapters replace capabilities observed in Test4, not recovered original source.
Test4 disassembly confirms its BitmapInfo write is 20 bytes. Pixel buffers are
copied into guest allocations; no host pointer is handed to ARM32 code. Android
adapter execution is unverified. Native export and dependency sets match Test4.

## Diagnostic changes

- `ZB_LOAD_TRACE=1` enables bounded JIT timeslices. The thread itself records PC,
  LR, SP, FP, CPSR, r0-r3, thread IDs, translated ticks, and mapped library offsets
  after Run returns. Up to three recent samples per thread are retained. This is
  not a guest signal; execution resumes with the same registers. It has overhead
  and can change timing, so Test5 is for diagnosis.
- Mapping metadata is protected while concurrent threads describe addresses.
- Guest loader stages distinguish scanning, guest malloc, dlopen/dlsym, binding,
  JNI_OnLoad and mapped-library sweeping. A library can stall inside constructors
  before JNI_OnLoad; absence of JNI_OnLoad is not itself an error.
- The JNI history includes its cumulative count to distinguish activity from a
  repeated stale ring. Watchdog state now preserves `in_progress` on the first
  recorded call and when formatting a stuck-thread sample.
- Bounded Java stack samples run at 5, 20 and 45 seconds after guest process start.

## Validation and limits

- NDK r29 Android arm64 Release compile/link: PASS.
- x86_64 host JIT: ARM arithmetic loop (2,000,000 iterations) produces identical
  results with tracing off/on and records only enabled samples: PASS.
- Watchdog regression tests, including the two `in_progress` paths: PASS.
- APK v2 signature and 16 KiB ZIP alignment: PASS.
- Original DEX-code and asset preservation, new DEX checksum/class set and
  invoke-super target, manifest changes, ELF architecture/alignment/export and
  dependency checks: PASS.
- The host tests are focused diagnostic tests, not the full ARM64 Android runtime
  suite. There is no Android device execution or gameplay claim.

## Installation and next device observation

Package: `com.zettabridge.blockheadstest5`, versionCode 20261014.
It installs separately because the Test4 runtime signing key was not supplied.
Keep Test4 and its data. Import the already-working Guest2 APK with the
PendingIntent fix into Test5, launch once, wait at least 50 seconds, then return
to the launcher and copy its Last run report. Do not repeatedly tap launch while
the guest is still loading. No data/cache reset is required.

Expected new evidence: `jni-loader-stage`, `jni-loader-call`, `watch-pc-*`, JNI
`total=...`, and `Test5 stack +5s/+20s/+45s`. These should locate the stalled
constructor, loop or wait before changing guest synchronization or startup code.

## Rebuilding

1. Clone the pinned source above and initialize its Dynarmic submodule at
   `86458a0bd369d63ba4c2ef812cacbb6c9080c065` (the repository gitlink).
2. Apply the two `third_party/patches/dynarmic-000*.patch` files inside the
   Dynarmic checkout. Apply the accompanying Test5 source patch at the repo root.
3. Configure the root CMake project with NDK r29, ABI arm64-v8a, platform android-29,
   Release, ZB_BUILD_TESTS=OFF and Boost 1.87 headers; build target `zbridge`.
   With CMake 4, also set CMAKE_POLICY_VERSION_MINIMUM=3.5.
4. Configure `tests/diagnostics` as a separate x86_64 host CMake project with the
   same Boost headers, build it, and run ctest there.
5. Run `tools/build_blockheads_test5.py --help`. Supply the included Test4 input,
   new libzbridge.so, JDK 17, SDK platform/build-tools 35, the included audit_apk.py
   directory, signing directory, and separate work/output paths. The signing
   directory takes experimental-key.pem and experimental-cert.pem. Use your own
   matching test certificate/key, or the original experiment's key. A different
   key cannot update an existing Test5 installation in place.

The install ZIP contains source and inputs, not downloaded toolchains or a private
signing key. No game APK or game assets are embedded in the launcher.
