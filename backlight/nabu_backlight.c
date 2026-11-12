/*
 * nabu-backlight: brightness for the Xiaomi Pad 5 (nabu) panel, from userland over /dev/pmem.
 *
 * Hardware (nabu device tree, read from the tablet): KTZ8866 backlight driver at I2C address 0x11 on
 * soc/i2c@880000 = QUPv3 wrapper 0, serial engine 0 (GENI, clocks gcc 0x51 se, 0x79 m-ahb, 0x7a s-ahb),
 * enable GPIOs 27 (hwen), 114 (enp), 115 (enn). The boot firmware leaves the panel lit; brightness is the
 * 11-bit value in KTZ8866 registers 0x04 (bits 2:0) and 0x05 (bits 10:3).
 *
 * Brightness source: backboardd's current display brightness (BackBoardServices BKSDisplayBrightnessGetCurrent,
 * 0..1), what the Control Center and Settings sliders set. Polled every 150 ms; only changes are written.
 *
 * Safety: an access to a serial engine whose clocks are off stalls the bus. Every SE access happens only after
 * the GCC branch status bits say the three clocks run; if they do not, they are voted on first and checked again.
 * Each stage is logged ("bl: ...") to the kernel log through PMEM_LOG before it touches hardware.
 * Off unless boot-arg nabu-backlight=1.
 */
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/ioccom.h>
#include <sys/sysctl.h>
#include <unistd.h>

struct pmem_log { char text[240]; };
#define PMEM_LOG _IOW('P', 6, struct pmem_log)

static int fd = -1;

static void say(const char *fmt, ...)
{
	struct pmem_log l;
	memset(&l, 0, sizeof(l));
	int n = snprintf(l.text, sizeof(l.text), "bl: ");
	va_list ap;
	va_start(ap, fmt);
	vsnprintf(l.text + n, sizeof(l.text) - n, fmt, ap);
	va_end(ap);
	fprintf(stderr, "%s\n", l.text);
	if (fd >= 0)
		ioctl(fd, PMEM_LOG, &l);
}

static uint32_t rd(uint64_t pa)
{
	uint32_t v = 0xdeadbeef;
	if (pread(fd, &v, 4, (off_t)pa) != 4)
		say("read %llx failed: %s", (unsigned long long)pa, strerror(errno));
	return v;
}

static void wr(uint64_t pa, uint32_t v)
{
	if (pwrite(fd, &v, 4, (off_t)pa) != 4)
		say("write %llx failed: %s", (unsigned long long)pa, strerror(errno));
}

/* SM8150 GCC (as Linux gcc-sm8150.c): QUPv3 wrapper 0 branch clocks and their APCS vote bits. */
#define GCC		0x00100000ull
#define VOTE		(GCC + 0x5200c)
static const struct { const char *name; uint32_t halt, bit; } clk[] = {
	{ "wrap0 m-ahb", 0x17004, 6 }, { "wrap0 s-ahb", 0x17008, 7 }, { "wrap0 s0", 0x17030, 10 },
};

static int clocks_on(void)
{
	int all = 1;
	for (unsigned i = 0; i < 3; i++) {
		uint32_t cbcr = rd(GCC + clk[i].halt);
		/* Bit 1 (HW_CTL): hardware clock gating. Such a branch reads CLK_OFF while idle and runs on demand
		 * (batch 6: s-ahb 80000002), as Linux's BRANCH_HALT_VOTED/hwcg handling assumes. */
		int hwctl = (cbcr >> 1) & 1;
		int off = ((cbcr >> 31) & 1) && !hwctl;
		say("clock %s cbcr %08x %s", clk[i].name, cbcr, off ? "OFF" : hwctl ? "hw-gated (ok)" : "on");
		all &= !off;
	}
	return all;
}

/* GENI serial engine 0 of QUPv3 wrapper 0 (Linux qcom-geni-se.h / i2c-qcom-geni.c offsets). */
#define SE		0x00880000ull
#define GENI_STATUS		0x040
#define GENI_DMA_MODE_EN	0x258
#define TX_PACKING_CFG0		0x260
#define TX_PACKING_CFG1		0x264
#define I2C_TX_TRANS_LEN	0x26c
#define M_CMD0			0x600
#define M_IRQ_STATUS		0x610
#define M_IRQ_EN		0x614
#define M_IRQ_CLEAR		0x618
#define TX_FIFO			0x700
#define FW_REV			0x068
#define M_CMD_DONE		(1u << 0)
#define M_CMD_ABORT		(1u << 5)
#define M_GP_IRQ_NACK		(1u << 10)
#define M_TX_FIFO_WM		(1u << 30)
#define I2C_WRITE		1u

static int i2c_write(uint8_t addr, const uint8_t *data, unsigned len)
{
	if (len > 4)
		return -1;
	wr(SE + M_IRQ_CLEAR, 0xffffffff);
	wr(SE + I2C_TX_TRANS_LEN, len);
	wr(SE + M_CMD0, (I2C_WRITE << 27) | ((uint32_t)addr << 9));
	uint32_t word = 0;
	for (unsigned i = 0; i < len; i++)
		word |= (uint32_t)data[i] << (8 * i);
	wr(SE + TX_FIFO, word);
	for (int i = 0; i < 200; i++) {
		uint32_t st = rd(SE + M_IRQ_STATUS);
		if (st & M_CMD_DONE) {
			wr(SE + M_IRQ_CLEAR, st);
			return (st & (M_GP_IRQ_NACK | M_CMD_ABORT)) ? -1 : 0;
		}
		usleep(500);
	}
	say("i2c write to %#x timed out (irq %08x status %08x)", addr, rd(SE + M_IRQ_STATUS), rd(SE + GENI_STATUS));
	return -1;
}

static int set_level(unsigned level)	/* 0..2047 */
{
	uint8_t lsb[2] = { 0x04, (uint8_t)(level & 7) }, msb[2] = { 0x05, (uint8_t)(level >> 3) };
	return i2c_write(0x11, lsb, 2) | i2c_write(0x11, msb, 2);
}

int main(void)
{
	char args[1024] = "";
	size_t n = sizeof(args) - 1;
	sysctlbyname("kern.bootargs", args, &n, NULL, 0);
	fd = open("/dev/pmem", O_RDWR);
	if (!strstr(args, "nabu-backlight=1")) {
		say("off (no nabu-backlight=1)");
		return 0;
	}
	if (fd < 0) {
		fprintf(stderr, "bl: /dev/pmem: %s\n", strerror(errno));
		return 1;
	}
	say("start: KTZ8866 at 0x11 on QUP0 SE0 (0x880000)");
	if (!clocks_on()) {
		say("voting QUP0 m-ahb, s-ahb, s0 clocks on (vote reg %llx)", (unsigned long long)VOTE);
		wr(VOTE, rd(VOTE) | (1u << 6) | (1u << 7) | (1u << 10));
		usleep(1000);
		if (!clocks_on()) {
			say("clocks still off: not touching the serial engine");
			return 1;
		}
	}
	uint32_t fw = rd(SE + FW_REV), dma = rd(SE + GENI_DMA_MODE_EN);
	uint32_t p0 = rd(SE + TX_PACKING_CFG0), p1 = rd(SE + TX_PACKING_CFG1);
	say("se fw %08x (protocol %u) dma %u tx packing %08x %08x status %08x", fw, (fw >> 8) & 0xff, dma, p0, p1,
	    rd(SE + GENI_STATUS));
	if (((fw >> 8) & 0xff) != 3) {	/* GENI protocol 3 = I2C */
		say("serial engine is not in I2C mode: stop");
		return 1;
	}
	if (dma)
		wr(SE + GENI_DMA_MODE_EN, 0);	/* FIFO mode for these 2-byte writes */
	if (!p0) {				/* 8-bit words, four per FIFO word, LSB first */
		wr(SE + TX_PACKING_CFG0, 0x20e4380e);
		wr(SE + TX_PACKING_CFG1, 0x30f);
	}
	wr(SE + M_IRQ_EN, M_CMD_DONE | M_CMD_ABORT | M_GP_IRQ_NACK);

	void *bks = dlopen("/System/Library/PrivateFrameworks/BackBoardServices.framework/BackBoardServices", RTLD_NOW);
	float (*current)(void) = bks ? (float (*)(void))dlsym(bks, "BKSDisplayBrightnessGetCurrent") : NULL;
	say("BKSDisplayBrightnessGetCurrent %s", current ? "found" : "missing: fixed 60%");
	int last = -1, fails = 0;
	for (;;) {
		float b = current ? current() : 0.6f;
		if (b < 0) b = 0;
		if (b > 1) b = 1;
		unsigned level = 24 + (unsigned)(b * b * (2047 - 24));	/* perceptual curve, never fully dark */
		if ((int)level != last) {
			int rc = set_level(level);
			if (last < 0 || rc)
				say("brightness %.3f -> level %u: %s", b, level, rc ? "FAILED" : "ok");
			if (rc && ++fails > 20) {
				say("too many I2C failures: stop");
				return 1;
			}
			last = (int)level;
		}
		if (!current)
			pause();
		usleep(150000);
	}
}
