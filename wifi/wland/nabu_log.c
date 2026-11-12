/* nabu: line-buffered copy of stdout/stderr into the kernel log (see nabu_log.h). */
#define NABU_LOG_IMPL
#include "nabu_log.h"
#include <fcntl.h>
#include <string.h>
#include <unistd.h>
#include <sys/ioctl.h>
#include <sys/ioccom.h>
/* -include nabu_log.h already defined the redirections for this file too: undo them here */
#undef printf
#undef fprintf
#undef puts
#undef putchar

struct pmem_log { char text[240]; };
#define PMEM_LOG _IOW('P', 6, struct pmem_log)

static int log_fd = -2;
static char line[240];
static size_t used;

static void flush_line(void)
{
	if (log_fd == -2)
		log_fd = open("/dev/pmem", O_RDWR);
	if (log_fd >= 0 && used) {
		struct pmem_log l;
		memset(&l, 0, sizeof(l));
		memcpy(l.text, line, used < sizeof(l.text) - 1 ? used : sizeof(l.text) - 1);
		ioctl(log_fd, PMEM_LOG, &l);
	}
	used = 0;
}

static void feed(const char *s, size_t n)
{
	for (size_t i = 0; i < n; i++) {
		if (s[i] == '\n' || used == sizeof(line) - 1)
			flush_line();
		if (s[i] != '\n')
			line[used++] = s[i];
	}
}

static int vout(FILE *f, const char *fmt, va_list ap)
{
	char buf[1024];
	va_list copy;
	va_copy(copy, ap);
	int n = vsnprintf(buf, sizeof(buf), fmt, copy);
	va_end(copy);
	int r = vfprintf(f, fmt, ap);
	if (n > 0)
		feed(buf, (size_t)n < sizeof(buf) ? (size_t)n : sizeof(buf) - 1);
	return r;
}

int nabu_printf(const char *fmt, ...)
{
	va_list ap;
	va_start(ap, fmt);
	int r = vout(stdout, fmt, ap);
	va_end(ap);
	return r;
}

int nabu_fprintf(FILE *f, const char *fmt, ...)
{
	va_list ap;
	va_start(ap, fmt);
	int r = (f == stdout || f == stderr) ? vout(f, fmt, ap) : vfprintf(f, fmt, ap);
	va_end(ap);
	return r;
}

int nabu_puts(const char *s)
{
	feed(s, strlen(s));
	feed("\n", 1);
	return puts(s);
}

int nabu_putchar(int c)
{
	char ch = (char)c;
	feed(&ch, 1);
	return putchar(c);
}
