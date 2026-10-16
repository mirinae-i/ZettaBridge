# Blockheads Test10: native screen mode and tracing cost

## Evidence

The user's Test9 run creates and renders a world. It records 974552 GL calls and
1596 native swap calls, with no recorded GL/EGL error. Those are lifetime counts,
not a steady-state FPS measurement. The old October 11 wrong-thread exceptions
are retained history. The current run ends by USER_REQUESTED task removal.

The Java view is 1080 x 2520, while the game's fixed surface is 1125 x 2436.
The different aspect ratios predict about 7.8 percent vertical stretching. The
world screenshot's roughly 66 x 144 pixel terrain cells show a substantially
larger distortion than the UI; the size mismatch alone does not explain it.
There is no device GPU capture or frame-time profile in this environment.

Original libApplication.so (SHA256
733d821027d69de329d0ba171df2e6013d612edf5a4d327badd001acc30b94c7)
selects +[UIScreenMode emulatedMode:11] in main at RVA 0x9c5260. Mode 11 selects
the best preset, including the 1125 x 2436 preset. Mode 12 selects the existing
UINativeScreenMode path, whose size uses Android real display metrics. It also
uses the native mode's existing content scale; UI size can change. This is a
candidate aspect-ratio correction, not a verified cure for the 3D distortion.

## Changes

- Opt into native screen mode for the exact supported game build, after its
  library load and before Java starts MainThread.nativeRun. Check the build ID,
  code fingerprints and the not-started flag. Change only movw r5,11 to movw
  r5,12 in the private mapped image. Restore page protections. Neither the
  original APK nor the extracted library on disk is changed. Unknown builds
  retain their original mode and log a skipped reason.
- Disable forced ZB_LOAD_TRACE. Test9 enables instruction cycle counting and
  leaves the JIT every 200000 ticks for diagnostic sampling. Ordinary syscall,
  JNI, error, exit and report functionality remains enabled.
- Count GL calls with a relaxed atomic; notify the report writer on the first
  call and every 4096 calls. First error and exit records remain immediate.
  Cache the host thread ID in TLS, avoiding a gettid syscall on every GL call.
- Add read-only world dimensions, framebuffer dimensions and projection matrix
  diagonal samples to the bounded display diagnostics. Retain owner-thread
  configuration dispatch, file locks, eventfd and the canonical APK path fix.

No save data, consent, purchase, licensing or guest-exit behavior is changed.
The game and QEMU are not redistributed. The launcher translates ARM32 native
code; this is not a native ARM64 build of the game itself.

## Verification

- Release Android arm64 libzbridge.so builds successfully.
- Host tests cover exact concurrent GL counts, first-call metadata, sampled
  notifications, unlocked observer callbacks and reset behavior.
- The native-screen guard test covers build mismatch, already-started state,
  instruction mismatch, overflow, exact changed byte, unchanged neighboring
  bytes, repeat calls and restored read/execute protections.
- Native layout/fingerprint verification passes against the original game SO.
- The host JVM exercises the actual addon source: configuration dispatch,
  restoration, chaining, exception propagation, activity discovery, EGL
  forwarding and the launch environment settings. It is not an Android UI test.
- APK checks preserve the package, runtime assets, permissions, activity
  declarations, prior native exports, library dependencies and canonical path
  bytecode. The primary DEX changes only the report label and checksums. The
  addon is rebuilt. Signature verification and 16 KiB alignment must pass.

Actual phone rendering, rotation/folding, touch coordinates, steady-state FPS
and stuttering remain unverified for Test10. Do not claim a device speedup from
the host checks. Compare the same world after warmup, first on the cover display
and then unfolded. Capture Last run report after 30-60 seconds if distortion or
stuttering remains. Relevant new fields are jni-screen-mode, framebufferWidth,
framebufferHeight, worldWidth, worldHeight, projectionX and projectionY.

## Rebuild

Apply the supplied source patch to Test9 commit 41df8e3, or the cumulative patch
to d6066b9b9e61de27041ba6e1f3c499c080c9e2b7. Retain the two supplied Dynarmic
patches; do not update its gitlink. Use NDK r29, SDK/build-tools 35, JDK 17,
Boost headers and CMake/Ninja as described in CLAUDE.md.

Build zbridge for Android arm64/API29 in Release mode. Then run:

```sh
python3 tools/build_blockheads_test10.py \
  --base /path/to/Test9-base.apk \
  --native /path/to/build/android-arm64/core/libzbridge.so \
  --jdk /path/to/jdk17 --sdk /path/to/sdk \
  --audit-dir /path/to/audit-tools --signing /path/to/private-signing \
  --work /path/to/build-work --out /path/to/Test10.apk
python3 tools/verify_blockheads_test10.py \
  --base /path/to/Test9-base.apk --apk /path/to/Test10.apk \
  --native /path/to/build/android-arm64/core/libzbridge.so \
  --out /path/to/apk-verification.json
```

The pinned Test9 base SHA256 is
89cb8da5046d953ecced711e5f068a93cf5a3ec1afe17bb0369da858d4f70208.
The audit-dir supplies audit_apk.py (the source copy is tools/test5_audit_apk.py).
The private signing key is not included. The original signer is required for
an in-place update. A different signer cannot update the installed package.

Identity: com.zettabridge.blockheadstest5, versionCode 20261019,
versionName 0.1.0-blockheads-test10-native-screen. The class name Test8Application
is retained for binary compatibility. Diagnostic prefixes now say Test10. The
report header is zettabridge-diagnostic-report10 (no space before 10), preserving
the primary DEX string length and all bytecode offsets.
