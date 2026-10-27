@ Guest4 native-mode continuation, assembled at virtual address 0xe31d00.
@ Entry: s0 = nativeWidth / points, s2 = the Test11/12 points denominator.
@ The host only selects points > 600 on near-square, density-valid panels.
@ Preserve all registers and status except the intentionally adjusted s0.
@ No calls, absolute pointers, allocation, or per-frame work.
push {r0, r1, r2, r3}
mrs r3, apsr
vmrs r2, fpscr
vmov r0, s2
ldr r1, min_points
cmp r0, r1
bls unchanged
ldr r1, max_points
cmp r0, r1
bhi unchanged
vpush {d1}
vldr s2, size_ratio
vmul.f32 s0, s0, s2
vpop {d1}
unchanged:
vmsr fpscr, r2
msr apsr_nzcvq, r3
pop {r0, r1, r2, r3}
@ Displaced instruction from +[UINativeScreenMode nativeMode:].
vstr s0, [fp, #-24]
b #0x26d864
min_points:
.word 0x44160000
max_points:
.word 0x442a8000
size_ratio:
.word 0x3f666666
