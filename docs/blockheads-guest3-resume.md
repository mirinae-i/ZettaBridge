# Blockheads Guest3: service window messages during surface waits

## Report and scope

The October 28 Test12 report shows normal rendering in guest PID 28107, followed
by `onPause` returning at 06:49:13.705. It contains no later `onStart` or
`onResume`. Its native snapshot was written at 06:49:13.049, before the pause;
it is not a stack capture of the freeze. The wrong-thread exceptions are from
October 17. The latest GMS exception was caught before normal gameplay. Do not
attribute this report to those historical exceptions or claim an observed ANR.

Inspection of the supplied Guest2 APK exposed a reproducible wait cycle:

1. `MainThread.tick` calls the surface tick action before processing messages.
2. `GLSurfaceView.readySurface` releases the old EGL window, acknowledges surface
   destruction, then waits indefinitely on `mLock` for a new surface.
3. Android can synchronously wait for a foreign-thread window root's handler in
   `WindowManagerGlobal.setStoppedState`, through `runWithScissors(..., 0)`.
4. The window owner cannot service that handler while waiting for a surface,
   and the Android main thread cannot finish stopping/restarting the window.

This cycle was reproduced with the original method and a host queue/renderer
fixture. It is a plausible explanation for the phone symptoms, not confirmation
from a frozen on-device stack. Relevant primary references:

- [AOSP foreign-thread stopped-state dispatch](https://android.googlesource.com/platform/frameworks/base/%2B/9bd11895d8f4c850ee28f6155ea9c65ea5c6d308%5E2..9bd11895d8f4c850ee28f6155ea9c65ea5c6d308/)
- [SurfaceHolder.Callback destruction contract](https://developer.android.com/reference/android/view/SurfaceHolder.Callback)

## Change

Only `readySurface()`, `surfaceCreated()` and `surfaceDestroyed()` in the guest's
`com.apportable.gl.GLSurfaceView` are replaced. One helper is added in
`classes4.dex`:

- Keep waiting while no valid surface exists; no render work proceeds in that
  state. Process the owner's Java message queue outside `mLock` and use a 50 ms
  idle wait because a Handler message does not notify that monitor.
- A surface callback running on the owner cannot wait for itself. Destruction
  releases the old EGL window on that owner before acknowledging the callback.
  Callbacks on other threads retain their acknowledgement waits.
- Remember interrupts in callback waits and restore the flag after the
  acknowledgement. Immediate reinterrupt inside `Object.wait` can busy-spin.
- Preserve the original EGL-context lifetime, create/resize notifications,
  Activity lifecycle, save operations and native code. No active flags, process
  restarts, fabricated lifecycle events or exception suppression are introduced.

The normal surface-ready path does not run the helper. The first wait attempts
one optional diagnostic entry:
`Guest3 resume fix: surface wait pumps owner messages`.

`GLSurfaceView.java.in` is a compile-only carrier. Its `readySurface` method is
compiled using javac and D8, then transplanted; its stub fields, constructor,
native declarations and nested helper class are never packaged. This keeps
compiler-generated monitor regions. The two callback replacements are smali.

## Installation and data

This is a **guest APK import**, not a replacement launcher. Keep Test12 installed.
The original launcher's private signing key is not available in this workspace;
re-signing that launcher would prevent an in-place update. A guest import does
not require its signer to match the installed launcher.

1. Exit the world through the game UI, close the guest, and export a backup using
   the launch icon's **Saves** shortcut.
2. Long-press **Blockheads - ZettaBridge**, open **Settings / Games**, choose
   **Import APK**, and select `Blockheads-1.7.6-guest3-resume.apk`.
3. Launch the existing game entry and check returning from another app several
   times, then screen lock/unlock. Repeat in the menu and in a saved world.

The supplied Test12 APK was inspected, not just repository source:
`LibraryActivity.importApk` stops the guest first, and
`PluginStore.importApk` calls `replaceDirectoryKeeping(..., "data")`. Importing
the same `com.noodlecake.blockheads` package retains its data directory; do not
delete the game entry, clear app data or uninstall Test12. The APK's manifest
and game version are unchanged, so the launcher report still says Test12.
Existing PPI scaling, direct launch, offline crystals and save tools remain in
that launcher and apply to this guest's unchanged native image.

Rollback: close the guest and import the original Guest2 APK in the same way.
This changes code without intentionally resetting worlds or crystal balances.

## Build and verification

Inputs: user-supplied Guest2 APK, JDK 17, Apktool 2.11.1, Android build-tools 35,
and a separate guest-only signing key/certificate. Do not commit the game or
private key. The builder rejects any input other than this SHA-256:

```text
db72a693c59a930e311869b8989a4fc61d6c5699c161915025096ce045b40fac
```

```sh
python3 tools/build_blockheads_resume.py \
  --input /path/to/Blockheads-1.7.6-guest2-PendingIntent.apk \
  --apktool /path/to/apktool.jar --java /path/to/jdk/bin/java \
  --build-tools /path/to/build-tools/35.0.0 \
  --key /private/guest.pk8 --cert /private/guest-cert.pem \
  --work /path/to/new-build-directory \
  --out /path/to/Blockheads-1.7.6-guest3-resume.apk
```

The builder compares all 771 primary-DEX classes symbolically, excluding only
the three edited methods. The compiled `readySurface` method must match the
final APK's disassembly. All other 999 ZIP entries outside the primary DEX and
signatures retain identical bytes, including native libraries, secondary DEX,
resources and manifest. The new DEX contains only `SurfaceWait`, never the
compile-only stubs. The APK passes ZIP integrity, v1/v2 signature verification
and 16 KiB ZIP alignment checks.

For the regression, decompile `com.apportable.gl.GLSurfaceView` from the input
and output APKs with JADX 1.5.3, then run:

```sh
python3 tools/test_blockheads_resume.py --java /path/to/jdk/bin/java \
  --original-source /path/to/original/GLSurfaceView.java \
  --fixed-source /path/to/patched/GLSurfaceView.java \
  --build-work /path/to/new-build-directory --work /path/to/test-work
```

JADX cannot reconstruct the patched `readySurface` Java control flow. The test
uses its actual production source and requires the D8-generated method to match
the delivered APK's disassembly; the original method and both patched callbacks
are extracted from the actual decompilations. EGL and the Android message queue
are host fakes, not an Android emulator. Results:

```text
RED confirmed: original owner queue stalls until an impossible future surface
PASS stop handler completes without a surface; rendering resumes after recreation
PASS 30 pause/return cycles, including callbacks on the render owner
PASS exception propagation releases monitor; interrupted callbacks acknowledge before reinterrupting
```

Delivered APK: 99,719,717 bytes, SHA-256:

```text
4b680893ae1fd30374faceb7a19785b2bacb1ae7d5bf68271420b38f0cf4d55c
```

No ART/device, real GPU, world persistence or post-import phone test was run
here. Target-device acceptance remains open. If freezing remains, obtain a new
report after attempting the return and, if possible, an ANR/Java thread dump;
the pre-pause native snapshot cannot identify that later wait.
