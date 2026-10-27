# Blockheads Guest4: slightly smaller UI on PPI-adjusted panels

## Request and branch boundary

The user requested merging all existing work into `master`, then a slightly
smaller UI on their unfolded display. `master` was fast-forwarded from Test9
(`94cc74e5fefb4651a5e5dde32af62c8731c682d0`) to the Guest3 pause/return commit
(`b705383afa9c4dde180a3d695cedc94545764e4a`). This explicitly supersedes the older
handoff instruction to keep master at Test9. Guest4 is the next change on develop.

The supplied Test12 report identifies a 2256 x 2504 display, physical x/y PPI
around 421, and the existing 681.818-point policy limit. Do not infer phone PPI
from a screenshot resized for the conversation. Increasing only the Java policy
limit would not work with the installed launcher: its native guard accepts only
600 through 682 points. Its original private signing key is unavailable, so this
change is an importable guest APK for that existing Test12 installation.

## Change

Guest4 multiplies the game's native screen-mode scale by **0.9** when the existing
host policy selected `600 < points <= 682`. For the reported display, this reduces
UI width and height by about 10 percent relative to Guest3/Test12; the effective
logical width increases from 681.818 to about 757.576 points. It is a proportional
adjustment on top of the existing PPI policy, not a new claim of physical sizing.

The Test11/12 policy selects more than 600 points only on near-square panels with
usable physical PPI or logical-density fallback. Cover/phone panels that select
600 points are unchanged. A near-square panel whose policy still selects 600 is
also unchanged. Density detection and this adjustment are startup snapshots;
live folding or resizing is not newly handled here.

The patch runs once per native screen-mode construction, immediately after its
`nativeWidth / points` calculation. It returns through the original scale
constructor. Native pixel width/height, screen-mode selection, framebuffer and
touch conversion code are not edited. It does not render at a lower resolution
or upscale a finished image. Original icon/font artwork is unchanged, so smaller
UI is not a guarantee that all perceived blur disappears. This is not a frame-rate
optimization or a device-verified image-quality fix.

All Guest3 DEX files, including the pause/return correction, and its manifest,
resources and other libraries are byte-identical. Only `libApplication.so`, APK
signatures, and the added `assets/ZETTABRIDGE-GUEST4.txt` marker differ.

## Exact-build native patch

The builder rejects an unknown Guest3 APK or game library by SHA-256. The ARM
source is `android/guest-ui/native_ui_scale.S`:

- Replace the instruction at `0x26d860` with a branch to verified zero padding at
  `0xe31d00`. The original instruction stores the computed scale on the stack.
- Apply the bounded multiplier, replay that store, and return to `0x26d864`.
  Preserve general registers, stack, other VFP registers, FPSCR and APSR flags.
- Extend only the first executable PT_LOAD's file/memory size by the 88-byte
  continuation. Its rounded page extent is unchanged; the following writable
  segment begins at `0xe32000`. No allocated section is overwritten.
- Code and literal addressing are relative. There are no new native imports,
  callbacks, allocations or JNI calls.

Only those program-header size words, the four-byte branch, and the 88-byte
continuation may change. The original GNU build ID is deliberately retained for
Test12 compatibility; use the new full-library hash to identify this derivative.
Test12's screen-mode/points fingerprints and offline-crystal handler bytes are
unchanged. Its diagnostics will still report the original policy points and
Test12 launcher version; the extra multiplier is in the guest.

## Build and verification

Dependencies: Python with `keystone-engine==0.9.2`, `pyelftools`, `unicorn==2.1.4`,
JDK 17, Android build-tools 35, the verified Guest3 APK, and a guest-only signing
key/certificate. Do not commit game binaries or keys.

```sh
python3 tools/build_blockheads_ui.py \
  --input /path/to/Blockheads-1.7.6-guest3-resume.apk \
  --java /path/to/jdk/bin/java --build-tools /path/to/build-tools/35.0.0 \
  --key /private/guest.pk8 --cert /private/guest-cert.pem \
  --work /path/to/new-build-directory \
  --out /path/to/Blockheads-1.7.6-guest4-small-ui.apk

python3 tools/test_blockheads_ui.py \
  --original /path/to/original/libApplication.so \
  --apk /path/to/Blockheads-1.7.6-guest4-small-ui.apk \
  --out /path/to/guest4-ui-proof.json
```

Verification completed:

- Execute the original and delivered ARM `nativeMode:` method, including the
  continuation and scale argument supplied to `initWithScale:`, at two load
  addresses. Twelve comparisons cover cover-screen, reported unfolded, rotated
  unfolded, intermediate-density, 600-point and upper-bound cases. The original
  fails the smaller-size requirement; Guest4 supplies the expected scale. All
  calls and the method return/stack contract match.
- Twenty continuation cases verify register/status preservation, the original
  stack store, boundary values, invalid points, infinity and NaN.
- Preserve Test12 screen/crystal patch fingerprints and build-ID compatibility.
- Compare 1,001 unchanged ZIP entries against Guest3, including all DEX files and
  the manifest; verify the delivered native bytes against authored assembly.
- Pass ZIP integrity, v1/v2 signature verification, and 16 KiB ZIP alignment.

Unicorn models native display width, logging and Objective-C dispatch boundaries.
It is not Android or a GPU. Touch alignment, real pixel output, fold/unfold, saved
worlds and pause/return still require target-device confirmation. Existing Guest3
resume regression results apply to its unchanged DEX; they are not phone tests.

SHA-256 identifiers:

```text
Guest3 input APK:
4b680893ae1fd30374faceb7a19785b2bacb1ae7d5bf68271420b38f0cf4d55c
Original libApplication.so:
733d821027d69de329d0ba171df2e6013d612edf5a4d327badd001acc30b94c7
Guest4 libApplication.so:
e166b3a6c9f1cbb39f516b362225962ea745d6ad4164facd67fe96aa6c4014af
Guest4 delivered APK:
9ef1244fdcfd8563a7395f52adf883263ff26faa88611a6463e9770bcd2f16e3
```

## Apply or roll back

Save and exit the world. Back up with the existing launch icon's Saves shortcut,
then close the guest. Open the icon's Settings shortcut, select Import APK and
choose `Blockheads-1.7.6-guest4-small-ui.apk`. Keep the existing Test12 launcher and
game entry. Its verified import path preserves the same package's `data` folder.
Do not install this APK as a standalone Android application or uninstall Test12.

Start with the inner display unfolded. Check corner controls, item toolbar,
crystal dialog, menu text and touch alignment. Repeat a pause/return cycle, then
fully close and start on the cover display to confirm its scale is unchanged.
Rollback is a same-package import of Guest3, retaining its resume correction.
