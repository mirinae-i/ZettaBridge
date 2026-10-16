# Blockheads Test11: PPI-aware UI and direct launch

## Request and scope

The user supplied an unfolded, near-square menu screenshot and asked for a
slightly smaller UI using the current panel's PPI. The screenshot is not a PPI
measurement, and no model-specific density is assumed. Test10's native mode
computes its content scale from VerdePluginNativeWidth / 600; screen width alone
can produce large UI on an unfolded panel.

At guest-process launch, the addon reads the active default display's real
DisplayMetrics. This matches the full-display coordinate space used by the
existing native mode. It uses the geometric mean of plausible xdpi/ydpi as the
physical PPI. Nonfinite, out-of-range (72..1000) or strongly inconsistent axes
(ratio over 1.2) fall back to densityDpi, explicitly labelled as logical density.
If neither is usable, the Test10 scale remains unchanged.

The policy applies only when longer/shorter is at most 1.35. The target is
PPI / 160 pixels per game point, using Android's 160-dpi baseline. Since the
request is for a small adjustment, the chosen scale is clamped between 88 and
100 percent of Test10's scale. It never enlarges the UI. This is a bounded move
toward physical sizing, not a claim of exact physical sizing on every panel.
Narrow cover displays retain their prior size. One uniform scale applies to
both axes; native surface dimensions and the game's touch/layout path remain
unchanged. There is no new work per frame.

Public API references:
- https://developer.android.com/reference/android/util/DisplayMetrics
- https://developer.android.com/reference/android/view/Display#getRealMetrics(android.util.DisplayMetrics)

The real-metrics API is deprecated for window sizing; its deliberate use here
matches the original game's native full-display mode. Multi-window sizing and
live panel migration are not implemented by this patch. The scale is selected
at startup, before the guest main entry. Relaunch the game after folding or
unfolding to select the other panel's scale. Do not claim live fold handling.

## Native change

The existing exact-build/startup guards remain. In addition to Test10's screen
mode 11 -> 12 selection, Test11 adjusts the private float literal at RVA
0x26d904. In +[UINativeScreenMode nativeMode:], vldr s0 at 0x26d824 reads this
600.0 literal, and the division at 0x26d85c uses it to calculate the scale.
The prologue and both instructions are checked. No projection matrix, lifecycle
flag, consent state, game data, view transform or input coordinate is patched.
The original APK and library on disk are not changed.

Java publishes ZB_BLOCKHEADS_UI_POINTS, bounded again by native code to 600..682.
Both pages must be made writable before either is changed. Original page
protections are restored, including a preparation failure on the second page.
The patch refuses unknown builds, altered literals/instructions, unreadable
memory, invalid policy values and already-started execution. Diagnostics include
raw density values/source, chosen points, relative size and native patch result.

## Direct launcher and icon

The signed update uses the same package and private signer as Test10. Its app
label is `Blockheads - ZettaBridge`. The new, original vector artwork is a
block-built Z/bridge, with an adaptive icon on API 26+ and a monochrome layer on
API 33+. It does not embed the original game's artwork or imply an official game
release. The APK is an unofficial compatibility launcher, not a native game port.

`BlockheadsLaunchActivity` is the sole MAIN/LAUNCHER entry in the host process.
It finds the already-imported `com.noodlecake.blockheads`, checks its existing
launchable metadata and archive, then calls the original
`PluginSwitchActivity.intent`. It never loads the native game on the Android main
thread or bypasses the existing process/task switch policy. A running copy of the
same game is brought forward; a stale/different guest follows the original switch
path. The transient entry finishes before resume and has its own task affinity.

A fresh/incomplete import or missing archive opens the existing library for
import/repair. The original game APK is not bundled. A long press on the new app
icon exposes the Settings shortcut (`Games and diagnostics`, localized in Korean)
to the original `LibraryActivity`; that activity remains explicitly accessible.
Existing game shortcuts remain unchanged. A home-screen shortcut pinned to the
old LibraryActivity may still open the library after an update; replace that old
shortcut with the new app-drawer entry if necessary.

The launcher ABI is verified against the pinned Test10 DEX, including `find`,
`isLaunchable`, `apk` and `PluginSwitchActivity.intent`. Compile stubs are not
packaged. The primary DEX changes only its same-length report version/checksums.
All 41 original runtime/license assets remain byte-identical. No saves, consent,
purchase handling or process-exit policy are changed.

## Verification

Passed in this workspace:
- Actual addon compilation against Android SDK 35 with JDK 17.
- Host JVM contracts using the actual addon: physical PPI takes precedence over
  logical density, a 456-PPI fixture gives a 5-percent reduction, the 12-percent
  cap, no enlargement, cover-screen behavior in both orientations, invalid PPI
  fallback, missing metrics, native width in landscape, and environment handoff.
- Existing owner-thread configuration dispatch/restoration, exception propagation,
  activity discovery and EGL forwarding contracts.
- Native patch test using GuestMemory: exact changed bytes on both pages,
  untouched neighbors, input/build/start guards, idempotence and RX restoration.
- Original libApplication.so build ID, code and literal layout verification.
- Build/verification Python syntax and Git whitespace checks.

These fixtures are not measurements of the user's device. Actual target-device
PPI, rendered UI size, touch alignment and folding behavior remain unverified.
The user restored the exact Test10 input in `source.zip` (SHA256
c67a1a53dfb8dcfd4fcc2ed88650e3c60c6b59acf7a77ef38d868109db9344b9); all 110
bundled SHA256 checks passed. Additional completed checks:

- Android arm64/API 29 Release compile and link with NDK r29, Boost 1.87 and
  pinned Dynarmic plus both tracked patches. An explicit writable TMPDIR is
  needed for the assembler in this workspace.
- Actual addon SDK 35/D8 compilation, including the direct-launch activity.
- Host launch contracts exercise real PluginRecord/PluginSwitchActivity code:
  cold/warm/different guest routing, first/incomplete/missing archive fallback,
  fixed game identity, and preservation of the save fixture.
- APK v1/v2 signatures, identical Test10 signer, increasing versionCode, ZIP and
  native ELF 16-KiB alignment, native exports/dependencies, all prior assets,
  scoped DEX/manifest changes, compiled adaptive/monochrome icon, settings
  shortcut and aapt2's sole launchable activity all pass.

Host launch contracts do not emulate Android task management. Actual target-device
launch/resume, shortcut UI, density behavior, touches and frame times still need
installation testing. The install ZIP includes the APK, source snapshot, pinned
Test10 input, hashes and build/verification evidence. It contains no private key,
original game or QEMU binary.

## Rebuilding

Use NDK r29 and the pinned Dynarmic revision/patches described in CLAUDE.md to
build the Android arm64/API29 Release core. Then use SDK/build-tools 35 and the
same private signer as Test10:

```sh
python3 tools/build_blockheads_test11.py \
  --base /path/to/Test10.apk --native /path/to/libzbridge.so \
  --jdk /path/to/jdk17 --sdk /path/to/sdk --audit-dir /path/to/audit-tools \
  --signing /path/to/private-signing --work /path/to/build-work --out /path/to/Test11.apk
python3 tools/verify_blockheads_test11.py \
  --base /path/to/Test10.apk --apk /path/to/Test11.apk \
  --native /path/to/libzbridge.so --out /path/to/apk-verification.json
```

Pinned Test10 SHA256:
e2fa636c94c554db4977fb42b5b5f5cd44acc99dd9588daad3aab8ac261418fa.
Expected in-place signer certificate SHA256:
415bc1f97da699964e09228ece388741405ab7b2e750f1946dd7a6a363e08ae0.
The builder reuses Test10's runtime assets and primary DEX, changing only the
same-length report header/checksums. The addon and core are rebuilt; launcher
resources and the scoped entry/shortcut manifest settings are compiled with aapt2. It keeps
com.zettabridge.blockheadstest5, uses versionCode 20261020 and versionName
0.1.0-blockheads-test11-ppi-ui, and retains the Test8Application ABI class name.
No private key or original game is committed or included in a public bundle.

Focused launch check:

```sh
python3 tools/test_blockheads_launch.py --jdk /path/to/jdk17 --work /path/to/launch-tests
```

Use `tools/package_blockheads_test11.py` after building/verification from a clean,
committed source tree. It records the commit/tree and includes no signing material.
The previous source-only handoff is superseded by this packaged build. Develop
contains Test10 and later work; master remains the Test9 boundary.
