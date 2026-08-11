/*
 * spf_tandem_regs_mmap.c
 *
 * Register access to the tandem block from userspace, by mapping the one page
 * the block occupies on the CPU interconnect.
 *
 * The address is fixed by the block design: `ad_cpu_interconnect 0x7C450000
 * i_tandem_agc` in system_bd.tcl. It is checked at open by reading the ID
 * register -- mapping the wrong page and then trusting whatever it returns is
 * how a capture thread ends up decoding another peripheral's registers as gain
 * events.
 */

#include "spf_tandem_fifo.h"

#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

#define SPF_TANDEM_BASE_ADDR 0x7C450000u
#define SPF_TANDEM_MAP_BYTES 4096u
#define SPF_TANDEM_ID_MAGIC  0x54414731u   /* "TAG1" */

typedef struct {
	volatile uint32_t *regs;
	int fd;
} spf_tandem_mmap_t;

int spf_tandem_reg_read(void *ctx, uint8_t addr, uint32_t *out)
{
	spf_tandem_mmap_t *m = ctx;

	if (m == NULL || m->regs == NULL || out == NULL)
		return -1;
	/* addr is uint8_t, so every value it can hold is inside the 4 KiB map --
	 * no bound check is possible or needed. Widening the address type later
	 * would need one. */
	*out = m->regs[addr >> 2];
	return 0;
}

int spf_tandem_reg_write(void *ctx, uint8_t addr, uint32_t value)
{
	spf_tandem_mmap_t *m = ctx;

	if (m == NULL || m->regs == NULL)
		return -1;
	m->regs[addr >> 2] = value;
	return 0;
}

void *spf_tandem_regs_open(void)
{
	spf_tandem_mmap_t *m;
	void *p;
	uint32_t id;

	m = calloc(1, sizeof(*m));
	if (m == NULL)
		return NULL;
	m->fd = open("/dev/mem", O_RDWR | O_SYNC);
	if (m->fd < 0) {
		free(m);
		return NULL;
	}
	p = mmap(NULL, SPF_TANDEM_MAP_BYTES, PROT_READ | PROT_WRITE, MAP_SHARED,
	         m->fd, SPF_TANDEM_BASE_ADDR);
	if (p == MAP_FAILED) {
		close(m->fd);
		free(m);
		return NULL;
	}
	m->regs = p;

	/* Verify before trusting. A bitstream without the block, or a block moved
	 * to another address, would otherwise have this thread decoding whatever
	 * peripheral happens to live here as gain events. */
	if (spf_tandem_reg_read(m, 0x00, &id) != 0 || id != SPF_TANDEM_ID_MAGIC) {
		munmap(p, SPF_TANDEM_MAP_BYTES);
		close(m->fd);
		free(m);
		return NULL;
	}
	return m;
}

void spf_tandem_regs_close(void *ctx)
{
	spf_tandem_mmap_t *m = ctx;

	if (m == NULL)
		return;
	if (m->regs != NULL)
		munmap((void *)m->regs, SPF_TANDEM_MAP_BYTES);
	if (m->fd >= 0)
		close(m->fd);
	free(m);
}
