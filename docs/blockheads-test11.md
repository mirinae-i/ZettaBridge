# Blockheads Test11: bounded PPI-aware UI scale

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

## Verification and current delivery limit

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
No Android native library link, APK assembly, signature/alignment verification
or on-device run was performed for Test11. The pinned Test10 APK is no longer
present in this workspace, and the GitHub repository contains source only.
The user must reattach the Test10 APK or its install ZIP to finish packaging.
Do not describe this source revision as a delivered installable Test11 build.

## Packaging when the Test10 input is restored

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
same-length report header/checksums. The addon and core are rebuilt. It keeps
com.zettabridge.blockheadstest5, uses versionCode 20261020 and versionName
0.1.0-blockheads-test11-ppi-ui, and retains the Test8Application ABI class name.
No private key or original game is committed or included in a public bundle.
