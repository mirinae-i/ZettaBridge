SECTIONS {
 .text 0xb60380 : { *(.text.entry) *(.text*) *(.rodata*) }
 /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment) *(.note*) }
}
