/* Linux arm64 Image entry, position independent; no inherited Redmi code. */
.section .text.head, "ax"
.global _head
_head:
    b _start
    .long 0
    .quad 0x80000 /* Match the stock Pixel arm64 Image text_offset. */
    .quad _end
    .quad 0xa
    .quad 0, 0, 0
    .ascii "ARM\x64"
    .long 0
.text
_start:
    msr daifset, #0xf
    mov x19, x0
    msr spsel, #1
    adr x1, _stack_top
    mov sp, x1
    adr x1, vectors
    mrs x2, CurrentEL
    cmp x2, #8
    b.eq 1f
    msr vbar_el1, x1
    b 2f
1:  msr vbar_el2, x1
2:  isb
    adr x1, _bss_start
    adr x2, _bss_end
3:  cmp x1, x2
    b.hs 4f
    str xzr, [x1], #8
    b 3b
4:  mov x0, x19
    bl probe_main
5:  wfe
    b 5b

.balign 0x800
vectors:
.rept 16
    b probe_exception
    .balign 0x80
.endr
