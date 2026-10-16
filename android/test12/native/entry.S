.syntax unified
.arm
.section .text.entry,"ax",%progbits
.global patch_entry
patch_entry:
    adr r3, patch_entry
    movw ip, #0x0380
    movt ip, #0x00b6
    sub r3, r3, ip
    b grant
.global setup_entry
setup_entry:
    adr r1, patch_entry
    movw ip, #0x0380
    movt ip, #0x00b6
    sub r1, r1, ip
    bl setup
    sub sp, fp, #24
    pop {r4, r5, r6, r7, r8, r10, r11, pc}
