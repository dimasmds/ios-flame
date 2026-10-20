/*
 * First userspace program for SWEET bring-up: mockfs serves the RAM disk
 * itself as /sbin/launchd, so this static binary is PID 1. It proves that
 * exec, the user/kernel boundary, devfs and the console all work, then
 * stays alive (init exiting panics the kernel).
 *
 * tools/mkinit.py wraps the assembled __text into a static Mach-O, so this
 * must stay position independent with no relocations and no writable data:
 * every reference is adr (PC-relative), the PID digit lives on the stack.
 *
 * Raw XNU syscalls: number in x16, svc #0x80, carry set on error.
 */
#define SYS_write	4
#define SYS_read		3
#define SYS_close	6
#define SYS_open	5
#define SYS_getpid	20
#define SYS_select	93
#define O_RDWR		2

	.text
	.globl	_start
	.p2align 2
_start:
	/*
	 * The kernel enters a static binary with sp at argc, aligned only to
	 * what the argument/apple strings happened to need. Using a misaligned
	 * sp as a base register raises an SP alignment fault (SIGBUS) on real
	 * hardware (QEMU does not check), so align it like crt0/dyld do.
	 */
	mov	x9, sp
	and	x9, x9, #~15
	mov	sp, x9

	adr	x0, path
	mov	x1, #O_RDWR
	mov	x2, #0
	mov	x16, #SYS_open
	svc	#0x80
	b.cs	hang			/* no console: nothing to report to */
	mov	x19, x0

	adr	x1, hello
	adr	x2, hello_tail
	sub	x2, x2, x1
	bl	write_console

	mov	x16, #SYS_getpid
	svc	#0x80
	add	w0, w0, #'0'		/* PID 1 expected: one digit */
	sub	sp, sp, #16
	strb	w0, [sp]
	mov	x1, sp
	mov	x2, #1
	bl	write_console
	add	sp, sp, #16

	adr	x1, hello_tail
	adr	x2, alive
	sub	x2, x2, x1
	bl	write_console

#ifdef FLAME_HFS_TEST
	/* Read a separate file to prove that the HFS directory/data paths work. */
	adr	x0, check_path
	mov	x1, #0
	mov	x2, #0
	mov	x16, #SYS_open
	svc	#0x80
	b.cs	fs_fail
	mov	x20, x0
	sub	sp, sp, #64
	mov	x1, sp
	mov	x2, #22
	mov	x16, #SYS_read
	svc	#0x80
	b.cs	fs_fail_stack
	cmp	x0, #22
	b.ne	fs_fail_stack
	adr	x9, check_contents
	mov	x10, sp
	mov	x11, #22
fs_compare:
	ldrb	w12, [x9], #1
	ldrb	w13, [x10], #1
	cmp	w12, w13
	b.ne	fs_fail_stack
	subs	x11, x11, #1
	b.ne	fs_compare
	add	sp, sp, #64
	mov	x0, x20
	mov	x16, #SYS_close
	svc	#0x80
	b.cs	fs_fail
	adr	x1, fs_ok
	adr	x2, fs_ok_end
	sub	x2, x2, x1
	bl	write_console
	b	tick
fs_fail_stack:
	add	sp, sp, #64
fs_fail:
	adr	x1, fs_error
	adr	x2, fs_error_end
	sub	x2, x2, x1
	bl	write_console
	b	hang
#endif

tick:
	/* select(0, NULL, NULL, NULL, &5s) as a portable sleep */
	mov	x0, #0
	mov	x1, #0
	mov	x2, #0
	mov	x3, #0
	adr	x4, five_sec
	mov	x16, #SYS_select
	svc	#0x80

	adr	x1, alive
	adr	x2, alive_end
	sub	x2, x2, x1
	bl	write_console
	b	tick

/* write(x19, x1, x2) */
write_console:
	mov	x0, x19
	mov	x16, #SYS_write
	svc	#0x80
	ret

hang:
	b	hang

	.p2align 3
five_sec:
	.quad	5			/* tv_sec */
	.quad	0			/* tv_usec (int32 + padding) */
path:
	.asciz	"/dev/console"
hello:
	.ascii	"\n*** SWEET userspace: init running as PID "
hello_tail:
	.ascii	" ***\n"
alive:
	.ascii	"SWEET init: still alive\n"
alive_end:
#ifdef FLAME_HFS_TEST
check_path:
	.asciz	"/etc/flame-test"
check_contents:
	.ascii	"FLAME HFS RAM ROOT OK\n"
fs_ok:
	.ascii	"FLAME HFS: file read verified\n"
fs_ok_end:
fs_error:
	.ascii	"FLAME HFS: file read FAILED\n"
fs_error_end:
#endif
