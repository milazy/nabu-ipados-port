/* nabu: every line wland prints also goes into the kernel log (XNU2LOG) through /dev/pmem's PMEM_LOG ioctl,
 * because /private/var is a RAM volume and its files are gone after the next boot. Included with -include. */
#ifndef NABU_LOG_H
#define NABU_LOG_H
#include <stdio.h>
#include <stdarg.h>
int nabu_printf(const char *fmt, ...) __attribute__((format(printf, 1, 2)));
int nabu_fprintf(FILE *f, const char *fmt, ...) __attribute__((format(printf, 2, 3)));
int nabu_puts(const char *s);
int nabu_putchar(int c);
#ifndef NABU_LOG_IMPL
#define printf nabu_printf
#define fprintf nabu_fprintf
#define puts nabu_puts
#define putchar nabu_putchar
#endif
#endif
