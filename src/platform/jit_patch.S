.set mips32
.set noreorder
.text
.align 4
.globl h1_jit_patch_sync
.type h1_jit_patch_sync, @function
h1_jit_patch_sync:
    # JIT's patched JAL is at ra-8. v0 contains the resolved memory handler.
    # Do not clobber ra, gp, arguments, ARM registers, flags or cycle counter.
    sync
    cache 0x15, -8($ra)
    sync
    cache 0x10, -8($ra)
    sync
    jr $v0
    nop
.size h1_jit_patch_sync, .-h1_jit_patch_sync
