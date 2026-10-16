# Blockheads Test12: offline crystals and save backups

Test12 is an in-place update over Test11. It retains the package
`com.zettabridge.blockheadstest5`, signing certificate, direct launcher, adaptive
icon, bounded PPI policy and existing eventfd/rotation/runtime fixes. Its version
code is 20261021 and version name is `0.1.0-blockheads-test12-offline-saves`.
Work belongs on develop; master remains Test9. This is an unofficial compatibility
launcher. The original game APK and signing keys are not distributed.

## Local crystal buttons

For the supported Blockheads 1.7.6 ARMv7 image, the four crystal buttons become
ADD, adding 200, 1200, 3000 or 10000 to the existing local balance. The heading is
LOCAL CRYSTALS. The popup closes after a valid grant. No payment is attempted,
receipt synthesized, purchase callback spoofed or online service balance changed.
The existing free-offers button is not changed. Additions stop at a 10,000,000
balance to prevent overflow; no existing balance is reset.

The authored ARM handler is compiled from `android/test12/native`. At startup,
`prepare_blockheads_local_crystals` installs it in the private mapped image only
when `ZB_BLOCKHEADS_LOCAL_CRYSTALS=1`. The original APK/library on disk is unchanged.
The installer checks the exact build ID, the whole original TCUI button method's
FNV64 fingerprint, constructor instructions, CrystalManager method prologues,
startup flag, readable bounds and executable page permissions. Both pages are
prepared before writing and their permissions restored afterward. Unknown or
already-started images are skipped and diagnosed.

The constructor's product-query start call is suppressed. A small epilogue hook
sets the four existing button labels and enabled states. The handler matches the
actual button object, obtains CrystalManager.instance, calculates its normal
local consistency string and invokes the original `modify:modifyString:` with
a negative debit. The original method updates the amount/checksum, notifies
observers and marks it for saving. The existing `commitSaveIfNeeded` queues its
normal save operation. No code is added to the frame loop or input transform.

The generated header contains only our own C/assembly output. Reproduction uses
the user's original SO solely for guard checks and tests. Supported SO SHA256:
`733d821027d69de329d0ba171df2e6013d612edf5a4d327badd001acc30b94c7`.
Build ID: `81b7aa3ed0b95082858efc0a7a710115221c26b9`.

## Where data is stored

The paths below are derived from the launcher, original Java initialization and
native save/keychain functions; this workspace cannot inspect the phone's files.
PluginContext redirects the game's files directory to:

```
/data/user/0/com.zettabridge.blockheadstest5/files/plugins/com.noodlecake.blockheads/data/files/
```

LibraryManager sets HOME and CFFIXED_USER_HOME to that directory. GameView's save
enumeration uses NSApplicationSupportDirectory and appends `saves/`, giving:

```
.../data/files/Library/Application Support/saves/
```

Related game metadata uses `Library/Application Support/game/`. The original
Security default-keychain path is `$HOME/.Keychain.plist`, and CrystalManager
stores `com.majicjungle.blockheads.crystalcount` through that keychain interface.
Game preferences can also live in `Library/Preferences` or in the host's
`shared_prefs/com.noodlecake.blockheads__*.xml`. `/data/data` is the alternative
Android spelling of the same app-private location. No root access is needed by
the launcher to manage its own data.

## Save menu and behavior

Long press the new app icon and select Saves (localized in Korean). The original
Settings shortcut remains. Normal world saving/loading continues through the
game's own UI and autosave. Test12 adds portable whole-game ZIP export/restore,
not an attempt to serialize a running world or merge individual worlds.

The user first saves/exits the world and fully closes the game. The Saves screen
offers export, import, export of the previous restore backup, interrupted-restore
recovery, launch game and the original game/diagnostic library. Android's document
picker selects the input/output location; no storage permission is added. The
picker requests local documents. See the public API documentation:
https://developer.android.com/training/data-storage/shared/documents-files

Snapshots include the entire plugin `data` directory and only the game's
namespaced host preferences. This preserves worlds, keychain, settings and
supporting files even if a game version uses an additional subdirectory. It may
include caches/generated data and therefore be larger than a world-only export.
The game APK, extracted libraries/proxies, other plugins and external-storage
files are excluded. The ZIP is not encrypted.

Import validates a versioned game-specific manifest and every SHA256 before
showing a replacement confirmation. It rejects traversal, symlink sources,
duplicate/colliding names, unknown paths, wrong game, missing files, damaged
content, over 50000 entries, a manifest over 16 MiB, or over 2 GiB of expanded
data. Import replaces all worlds, crystal balance and settings together.

The guest process holds an OS shared file lock for its entire lifetime. Export,
restore and recovery require the exclusive lock. Starting a guest during these
operations exits that guest before runtime initialization. This prevents copying
active writers or stale memory from overwriting a restore. A pending journal
routes direct launch to recovery and independently blocks guest startup.

Restore validates into a private staging directory, exports the current data to
`files/zb-save-backups/before-restore.zip`, then writes a durable journal before
renaming the originals and replacements. Failure rolls back. After process death,
recovery rolls back an incomplete transaction or cleans up a committed one. If
recovery cannot finish, the journal remains and game launch stays blocked.
The previous snapshot can be exported separately. These checks cover process
death, not a guarantee against every power-loss/filesystem failure.

Uninstalling or clearing app storage deletes internal saves and the previous
snapshot. Export to a user-selected location first. Install this update over
Test11; do not uninstall to update.

## Verification and limits

Passed in the workspace:

- NDK r29 arm64/API29 Release build and SDK35/JDK17/D8 addon build.
- Authored ARM code plus original CrystalManager arithmetic/checksum/commit code
  in Unicorn at two load bases: all four quantities, invalid sender, cap,
  constructor/button setup and original consistency rejection (16 cases).
  Objective-C/UI and disk persistence boundaries are modeled; this proves save
  queue delivery, not a write on the Android phone.
- Native exact-build/startup/hash/protection guards and scoped memory edits.
- Actual SaveStore on the host JVM: complete round trip including keychain and
  both preference locations, six injected restore failures, process-death
  rollback, previous backup, seven malformed archives, symlink rejection and
  real cross-process locking.
- Actual Test12 addon PPI, owner-thread configuration, exception and EGL contracts;
  original direct-launch/switch contracts and interrupted-restore routing.
- APK v1/v2 signature and same certificate, ZIP/native ELF 16-KiB alignment,
  increasing version, preserved primary DEX code, prior runtime/license assets,
  native ABI/exports, compiled icons and both shortcuts, no new permissions.

No Android device/emulator is available here. Confirm ADD updates persist after
leaving/reopening the game, then export a small world, change it, restore the ZIP
and confirm its state. Device shortcuts/document picker and actual game reads of
restored files remain unverified. Existing Test11 folding/PPI limitations remain.

## Rebuild

The tracked generated ARM header is ready to compile; to reproduce and test it:

```sh
python3 tools/build_blockheads_crystals.py --ndk /path/to/ndk-r29 \
  --game /private/path/libApplication.so --work /path/to/arm-work
python3 tools/test_blockheads_crystals.py --game /private/path/libApplication.so \
  --code /path/to/arm-work/local-crystals.bin --out /path/to/crystal-contracts.json
```

The second command needs Unicorn and pyelftools. Build the native core as in
CLAUDE.md with pinned Dynarmic and both tracked patches, using a writable TMPDIR.
The install bundle includes its pinned Test11 base. Use the same private signer:

```sh
python3 tools/build_blockheads_test12.py --base /path/to/Test11.apk \
  --native /path/to/libzbridge.so --jdk /path/to/jdk17 --sdk /path/to/sdk \
  --audit-dir /path/to/audit-tools --signing /private/path/to/signing \
  --work /path/to/apk-work --out /path/to/Test12.apk
python3 tools/verify_blockheads_test12.py --base /path/to/Test11.apk \
  --apk /path/to/Test12.apk --native /path/to/libzbridge.so \
  --out /path/to/apk-verification.json
javac -d /path/to/save-tests android/test12/SaveStore.java tests/java/SaveStoreTest.java
java -cp /path/to/save-tests com.zettabridge.launcher.SaveStoreTest /path/to/empty-fixture
python3 tools/test_blockheads_display.py --jdk /path/to/jdk17 \
  --work /path/to/display-tests --source android/test12/Test8Application.java
python3 tools/test_blockheads_launch.py --jdk /path/to/jdk17 \
  --work /path/to/launch-tests --test12
```

Pinned Test11 SHA256:
`31115550c72bae1ccca250ccd576e95de72ca81e0a31d3553df8264f7123dcbf`.
Expected signer certificate SHA256:
`415bc1f97da699964e09228ece388741405ab7b2e750f1946dd7a6a363e08ae0`.
Package with `tools/package_blockheads_test12.py` only after committing the
source and rebuilding. The package includes source, base, hashes and evidence,
and excludes the original game and all private signing material.
