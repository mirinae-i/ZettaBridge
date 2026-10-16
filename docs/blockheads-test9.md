# Blockheads Test9: legacy eventfd wakeups

## Device evidence and scope

Test8 reports dated 2026-10-16, PIDs 18156 and 19395, have a valid attached
GLSurfaceView, EGL context and surface, and loadFinished=true. Nevertheless the
controller remains active=0, animating=0, glInitialized=0, frameDrawn=0, and
displayLinkPresent=0 after 15-30 seconds. Both native and Java swaps remain zero.
RunLoop.nativeNext and orientation/touch callbacks continue to arrive. This is
not evidence that world generation itself is blocked.

The two listed CalledFromWrongThreadException instances are dated October 11.
The landscape Test8 process ends with USER_REQUESTED / REMOVE TASK, not a new
Java crash. Its decor owner is Android main. This does not prove the foreign
owner-thread rotation workaround was exercised or that every rotation is fixed.

The original libApplication has SHA-256
733d821027d69de329d0ba171df2e6013d612edf5a4d327badd001acc30b94c7.
Static inspection identifies this sequence:

- UIApplication finishedLaunching (0x2414a0) completes launch and changes its
  application state to 0, then schedules a 200 ms dispatch_after on the main queue.
- The block at 0x241f54 calls the delegate's applicationDidBecomeActive:.
- EvolutionAppDelegate applicationDidBecomeActive: (0xcb467c) calls the game
  controller's didBecomeActive (0x782330), which marks it active and starts animation.

An unexecuted delayed activation therefore explains the observed state. It is
an inference about the phone, supported by the targeted reproduction below;
this development environment does not run the complete Android game UI.

## Runtime correction

ARM EABI eventfd (351) was missing; eventfd2 (356) was already implemented.
The original Apportable libSystem issues the older call while initializing
libdispatch's event machinery. Test9 translates it to the host's eventfd2 with
flags=0. The initial unsigned 32-bit count and normal host errors are preserved.
Unused guest argument registers are ignored. Existing eventfd2 flags are untouched.

This is a syscall compatibility fix, not a game patch. It does not force active
flags, synthesize lifecycle callbacks, alter timers, grant consent, or bypass
game exit. Existing file locking, canonical APK paths and Test8 Java code stay
in place. The old unimplemented-host-calls counter covers host-call stubs, not
missing Linux syscalls, so its zero value did not rule this defect out.

## Reproduction and validation

Two ARM32 programs run through actual before/after ARM64 Android core builds.
QEMU executes only the ARM64 development runner on this x86 host. It is never
bundled in the launcher. The runner uses the same libzbcore.a as libzbridge.so.

1. eventfd_legacy_dynamic.c checks the full unsigned initial counter, absence
   of implicit flags, a cross-thread epoll wakeup carrying a 64-bit increment,
   counter draining, EAGAIN, and unchanged eventfd2 semaphore/nonblocking/CLOEXEC.
   Test8 returns ENOSYS at creation. Test9 passes.
2. blockheads_dispatch_dynamic.c loads the user's original libv/libSystem with
   their constructors retained. It receives Mach notifications and drains the
   original dispatch main queue ONLY after a notification. Its immediate callback
   schedules a 200 ms delayed callback, like the launch sequence. Test8 runs the
   immediate callback but times out without the delayed one. Test9 receives the
   delayed callback once, after the deadline. This fixture requires no JNI UI.

The fixture's standard ELF metadata import fixups are the same as normal runtime
loading. It does not remove constructors or modify instructions. An earlier
periodic manual-queue-drain probe passed on Test8 and masked the wakeup defect;
that probe is not claimed as evidence of the fix. A standalone CFRunLoop probe
could not initialize a full CF environment and is not a passing test.

Run tools/test_blockheads_eventfd.py with --game ORIGINAL_GAME_APK, --base TEST8_APK,
--ndk-bin NDK_BIN, --qemu QEMU_AARCH64_STATIC, --before TEST8_RUNNER, --after TEST9_RUNNER,
and --out PROOF_DIRECTORY. It prepares private library copies, extracts the
unchanged runtime assets, builds both guest fixtures, checks expected failures
and successes, and writes logs plus results.json. Original game input SHA-256:
cae0371354dfda125793ba974c1f7a55b2161ed6d9c458f962da9eb468f8ec54.

The package contains runner source and its link command, but no runner binary,
QEMU, toolchain, private signing key, or game library. The runner is built against
each respective core revision. The remaining sched_get_priority_min/max ENOSYS
messages also occur in the passing dispatch fixture and are outside this fix.

## APK build and preservation

Continue the NDK r29 arm64-v8a/android-29 Release build described in
blockheads-test8.md. Build target zbridge. Test9 uses the same pinned Dynarmic
commit and patches, Boost headers and Android adapters. No remote push is needed.

Run tools/build_blockheads_test9.py with --base TEST8_APK, --native LIBZBRIDGE_SO,
--jdk JDK17, --sdk ANDROID_SDK, --audit-dir AUDIT_HELPER_DIRECTORY,
--signing PRIVATE_SIGNING_DIRECTORY, --work BUILD_DIRECTORY, and --out TEST9_APK.
The audit helper is source/test5_audit_apk.py copied as audit_apk.py, or the
equivalent tools/test5_audit_apk.py in this source tree. The base is pinned to:
bacce4296ed8c398742090b0caa0475212ae77fb24f87757c5dfab155b47010c.

The build retains classes2.dex byte for byte. Consequently the Application class
and individual display log prefixes still say Test8; the manifest and report
header identify Test9. The primary DEX changes only the report number and DEX
checksums. Original assets, permission list, target/min SDK, and signer remain
unchanged. The new core is ARM64 with 16 KiB-aligned load segments.

Run tools/verify_blockheads_test9.py with --base, --apk, --native and --out.
apksigner verify and zipalign checks are also performed during the build.
Package: com.zettabridge.blockheadstest5. Version code: 20261018.
Version name: 0.1.0-blockheads-test9-eventfd.
Test certificate SHA-256:
415bc1f97da699964e09228ece388741405ab7b2e750f1946dd7a6a363e08ae0.

## Next device gate

Update Test8 in place without deleting app data or reimporting the game. Check
portrait startup/world display, then rotate to landscape and back. If still
black, capture a fresh report after about 30 seconds, and a separate report
after rotation. Relevant evidence is active/animating/displayLinkPresent,
glInitialized/frameDrawn, javaSwaps/javaGoodSwaps and new dated exceptions.
Device gameplay, world creation and rotation remain unverified locally.
