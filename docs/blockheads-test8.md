# Blockheads Test8: configuration ownership and display diagnostics

## Input and device evidence

The supplied Test7 install archive SHA-256 is
b353ba011b1204dc14592ac0afe1cb69f684c8844079803c21bd60b03ecd8551.
Its launcher SHA-256 is
b199fd2e8e8b084f64e49c97483b019ff2673e4b0c84c7bbcbc98e23db0c7fcf.
Restore public source d6066b9b9e61de27041ba6e1f3c499c080c9e2b7 plus the
supplied cumulative Test7 patch. The original private signing key is required
for an in-place update and is not distributed.

The phone report shows 25 proxy loads, 168 native registrations and a successful
file lock. The previous Foundation loader and LMDB lock defects are past their
observed failure points. It does not establish successful world generation.

Two different processes must not be conflated:

- PID 7334 crashes on configuration change. ViewRootImpl expects Apportable's
  MainThread, but ActivityThread calls updateConfiguration on Android's main.
- PID 8763 continues running with only 15 native GL calls and then exit_group(0).
  The original libApplication code at 0x7849cc is the return address after the
  exit-alert button handler calls exit(0). Stack candidates are not an unwound
  backtrace. This exit evidence is not the rotation Java crash and is not a reason
  to disable normal game exit.

Native egl-swaps=0 alone cannot diagnose the black screen: this game also calls
Java EGL10.eglSwapBuffers, which bypasses that native counter.

## Scoped configuration workaround

Test8 installs an ActivityThread Handler callback after the existing guest runtime
has initialized. It inspects only transactions consisting entirely of exact
ActivityConfigurationChangeItem instances, only for the live VerdeActivity, and
only when the attached decor's owner is another thread.

For those transactions, it temporarily withholds Activity.mDecor while the
existing callback and framework handler run once on Android main. The framework
still updates activity resources and lifecycle on main. The decor is restored in
a finally block, and ViewRootImpl.updateConfiguration is posted to the decor's
existing Handler. Detached/replaced roots and destroyed activities are skipped.
No ViewRootImpl thread identity is rewritten. No orientation is locked. Original
framework and delivery exceptions remain errors rather than being swallowed.
Non-config, mixed, lifecycle, relaunch, and display-migration transactions keep
the normal path. An unsupported reflective API logs the reason and leaves normal
framework handling in place.

The dispatch contract was inspected in AOSP android-16.0.0_r1:

- https://android.googlesource.com/platform/frameworks/base/+/android-16.0.0_r1/core/java/android/app/ActivityThread.java
- https://android.googlesource.com/platform/frameworks/base/+/android-16.0.0_r1/core/java/android/app/servertransaction/ActivityConfigurationChangeItem.java
- https://android.googlesource.com/platform/frameworks/base/+/android-16.0.0_r1/core/java/android/app/servertransaction/ActivityTransactionItem.java
- https://android.googlesource.com/platform/frameworks/base/+/android-16.0.0_r1/core/java/android/app/servertransaction/ClientTransaction.java

This is a narrow compatibility workaround. Samsung API 37 implementation details
and actual device rotation are not locally verified.

## Read-only display probes

The host Application does not receive the plugin's activity lifecycle callbacks:
GuestInstrumentation replaces Activity.mApplication. Test8 therefore discovers
VerdeActivity through ActivityThread's live records, on main, for up to 60 seconds.
It posts display probes to Apportable's existing MainThread handler. One probe may
be pending at a time. Samples are reported near 0, 5, 15, 30 and 60 seconds after
discovery; the one-second polling is bounded to the first minute.

- Existing VerdeApplication.mGLView and its surface/EGL flags are read. The probe
  does not call getSurface(), which would create a view.
- A delegating EGL10/EGL11 proxy counts Java swap attempts and successes. Calls,
  return values, and original driver exceptions are preserved. Only error queries
  already made by the game are observed; there is no extra eglGetError call.
- A separate native probe checks the original game's GNU build ID and three code
  fingerprints before inspecting app/controller/display-link state. Class addresses
  are checked too. It reads the current Objective-C ivar-offset variables; initial
  offsets in the file are not valid after superclass layout adjustment.
- The native probe does not call Objective-C methods or write guest state. Java
  field inspection failure does not prevent the native probe from reporting.
- Native method counters retain up to 256 names and always print relevant
  MainThread, RunLoop and GLSurfaceRenderer lifecycle counters, including zero.

The probe's original libApplication SHA-256 is
733d821027d69de329d0ba171df2e6013d612edf5a4d327badd001acc30b94c7.
Build ID: 81b7aa3ed0b95082858efc0a7a710115221c26b9.
No consent, save, purchase, licensing, networking or game-exit behavior is changed.
The addon replaces Test7's fixed Java stack sampler with these display probes.
Native load tracing and the earlier runtime fixes remain enabled.

## Build and validation

Use the pinned Dynarmic gitlink 86458a0bd369d63ba4c2ef812cacbb6c9080c065 and
apply both existing third_party/patches/dynarmic-000*.patch files inside it.
Configure the root with NDK r29, arm64-v8a, android-29, Release,
ZB_BUILD_TESTS=OFF, Boost 1.87 headers, and CMAKE_POLICY_VERSION_MINIMUM=3.5
when using CMake 4. Build target zbridge. QEMU is not included or needed.

The shipped APK retains Test7 classes.dex except the report 7 -> 8 string and
DEX checksums, keeps every existing asset byte-for-byte, replaces classes2.dex
with Test8Application, and replaces only the ARM64 libzbridge.so. Rebuilding the
entire launcher from public Java sources would lose earlier custom DEX changes.
The manifest uses the same package com.zettabridge.blockheadstest5, versionCode
20261017, versionName 0.1.0-blockheads-test8-display-threads.

Run tools/build_blockheads_test8.py with --base (pinned Test7 APK), --native,
--jdk (17), --sdk (platform/build-tools 35), --audit-dir (containing the supplied
test5_audit_apk.py copied as audit_apk.py), --signing (original private key and
certificate), --work, and --out. The private key must never enter the archive.
Then run tools/verify_blockheads_test8.py with --base, --apk, --native, --out.

Focused checks:

- NDK Android ARM64 Release compilation and linking.
- tools/test_blockheads_display.py --jdk JDK --android android.jar --work DIR:
  reproduce foreign-root failure; route to owner; preserve framework main thread,
  callback chaining, decor restoration and errors; leave mixed/main-owned paths
  unchanged; discover plugin activity; preserve EGL11, call counts and exceptions.
- tools/verify_blockheads_display_layout.py ORIGINAL_LIB --out JSON, with
  pyelftools: check build ID, code fingerprints, class/ivar metadata, BSS singleton.
- tests/host/runtime_report_test.cpp: retain lifecycle counts beyond the old
  32-name bound and below the top-eight high-frequency calls.
- APK signature/signer continuity, duplicate entries, DEX scope/checksums/class
  set, all prior assets, manifest, ELF dependencies and 16 KiB ELF/ZIP alignment.

These checks are not an Android UI test. World generation and the black screen
are unresolved until device observations locate the missing render progress.

## Next device test

Install over Test7 without clearing data or reimporting the game. First launch in
portrait and wait 60 seconds at the black screen; return to the launcher and save
the report. Then test rotation and save a second report. Look for Test8
configuration routed/delivered, Test8 surface, javaSwaps/javaGoodSwaps, Test8
native display, and native-lifecycle lines for the current PID. If inspection is
unsupported, the explicit unavailable message is useful evidence.
