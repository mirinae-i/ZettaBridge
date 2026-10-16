# Blockheads Test7: ARM32 record locks and exit diagnostics

The Test6 phone run confirms that the canonical APK path fix got past Foundation:
all 25 proxies and 168 native registrations completed, and the game displayed its
multiplayer/data consent dialog. Selecting either option then ended the guest
process with EXIT_SELF, status 0. There were no recorded Java exceptions.

## Diagnosis and limits

The original libApplication.so has this startup path (ARM virtual offsets):

- EvolutionAppDelegate alertView:clickedButtonAtIndex:, 0xcb4a24: writes the
  original consent preference, then both choices call startThirdPartySDKs:.
- startThirdPartySDKs:, 0xcb32e8: continues through gdprCheckComplete, 0x7811c4.
- GameView init, 0x91c780: opens the app database. On failure it logs
  "Error. Unable to open app database." at 0x91cadc and calls exit(0) at 0x91caf0.
- DatabaseEnvironment initWithPath:maxDatabases:maxMapSizeInMB:, 0x662680, calls
  the bundled LMDB mdb_env_open at 0xdb8f88.

The old core returned EINVAL for ARM fcntl64 commands 5/6/7 and 12/13/14. The
classic fcntl syscall was also absent. Calling the original game's LMDB functions
in isolation reproduced mdb_env_open returning 22 (Invalid argument); the trace
reported unsupported commands 6 and 7. With this change, opening, committing a
key/value, closing, reopening, and reading the saved value all succeed.

This proves a runtime defect on the post-consent path and fits the phone's
exit(0) symptom. It does not prove that it is the only device startup problem.
No connected Android device, UI, ads, networking, or gameplay was tested here.
The original consent choices and their stored values are unchanged.

## Implementation

Translate ARM EABI flock (16 bytes) and flock64 (32 bytes) into the host flock,
including 64-bit offsets and command-number conversion. Use real host fcntl locks,
not a successful stub. Preserve errno, check guest memory access, bound GETLK
writeback, and return EOVERFLOW when a wide conflicting offset cannot fit in the
classic layout. Blocking SETLKW uses the existing interruptible syscall section.
The ARM classic syscall rejects wide command numbers, matching Linux compat.

NDK ARM32 header layout assertions and Linux compat behavior were checked against
https://github.com/torvalds/linux/blob/v6.12/fs/fcntl.c .

Previously the multithreaded exit_group fast path called _Exit before recording
an exit reason. It now persists guest-exit and PC/LR, plus at most 12 executable
address candidates from the first 1024 stack bytes. These are heuristic candidates,
not an unwound backtrace. Exit behavior remains unchanged. The JNI detail bound
is raised to 32 to accommodate these records and first file-lock results.
Test7Application retains load tracing/stack sampling and logs a Java VM shutdown
hook if that separate exit path is used. It does not suppress process termination.

## Validation

- NDK r29 ARM64 Android Release core compiles and links.
- NDK ARM32 layout assertions pass for both flock layouts.
- ARM32 guest / actual Android ARM64 core: GETLK owner/range, conflict errno,
  SETLK/unlock, classic fcntl, 64-bit offsets above 4 GiB, memory canaries, invalid
  and read-only pointers, wide-command rejection on classic fcntl, and overflow
  without partial output all pass.
- Both SETLKW variants remain blocked while the Python parent holds a conflicting
  lock for 250 ms, then complete after release.
- Original bundled LMDB: old core fails env_open with EINVAL; fixed core passes
  env_open, transaction commit, close/reopen, and saved-value verification.
- RuntimeReport host regression passes. A normal guest exit also persists the new
  exit details in the local fixture report.
- APK signature, signer identity, DEX/asset scope, manifest/package/version and
  16 KiB ELF/ZIP alignment are checked by the build and verification tools.
- Full Android startup and gameplay require the user's next device test.

QEMU runs the ARM64 test runner on the x86_64 development host only. It is not
included in or required by the APK. The runner uses the same ARM64 core archives
as libzbridge.so. The LMDB fixture disables ELF constructors in copies of game
libraries except libv so it can load without ART; it leaves all function code
unchanged and calls libv_init. No constructor patch is applied to the user's game.

## Rebuild and reproduce

Start from ZailoxTT/ZettaBridge d6066b9b9e61de27041ba6e1f3c499c080c9e2b7, apply
the included cumulative patch and the two existing third_party/patches/Dynarmic
patches. Build as described in blockheads-test5.md: NDK r29, Android 29, ARM64,
Release, Boost 1.87, ZB_BUILD_TESTS=OFF. Do not change the recorded submodule link.

tools/build_blockheads_test7.py takes the pinned Test6 APK, new libzbridge.so,
JDK 17, SDK platform/build-tools 35, an audit-dir containing test5_audit_apk.py
renamed to audit_apk.py, and the original experiment's signing key/certificate.
The signing key is not distributed. A different key cannot update Test6 in place.
Run tools/verify_blockheads_test7.py against the same inputs afterwards.

Pinned Test6 input SHA-256:
b333a34529cc2637bc03368496ccba8f4a7a6e941764df80ad1c90e3f320ae45.

Compile guest/tests/fcntl_locks_dynamic.c with the NDK ARM32 API21 compiler.
Run tools/test_fcntl_locks.py with --runner, --sysroot, --guest, --work, and an
optional --emulator for the host-development ARM64 runner. The driver must be a
different host process so its locks genuinely conflict with translated locks.

For the game-specific fixture, tools/prepare_blockheads_mdb.py takes the original
user-supplied game APK/ZIP and creates the local no-constructor library copies.
Compile tools/fixtures/blockheads_mdb.c with the same ARM32 compiler and -ldl.
Run it through the same core with target SDK 27, LD_LIBRARY_PATH pointing to the
guest stubs and those copies, DBPATH pointing to an empty temporary directory,
and PACKAGE_CODE_PATH/PACKAGE_RESOURCE_PATH set to the canonical original APK.
CFProcessPath is that APK path plus /com.noodlecake.blockheads. Match the remaining
Apportable environment used by the supplied fixture runner. The game and test
library copies are not redistributed.

## Device use

Install Test7 over Test6: same package com.zettabridge.blockheadstest5 and signer,
versionCode 20261016. Keep app data and the existing imported Blockheads entry.
No reimport or cache reset is needed. Launch once and select the consent option
the user wants; Don't Allow is sufficient for a first offline test. If it exits
again, send the report headed zettabridge-diagnostic-report 7. Check the current
run's guest-exit, jni-file-lock-*, and jni-exit-* lines, not old process records.

The install archive contains the launcher, source patches, pinned Test6 input,
and local test evidence. No game APK/assets, private keys, toolchains or emulator
binaries are included. This is still ARM32 execution through translation, not a
native ARM64 game port.
