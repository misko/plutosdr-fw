/* spf_tandem_fifo.c -- see the header for why the read order is the protocol. */

#include "spf_tandem_fifo.h"

#include <string.h>

/*
 * The 104-bit record, §7.1:
 *   [63:0]    sample_counter
 *   [71:64]   expected_index   (the index AFTER the transition)
 *   [75:72]   evt_reason
 *   [77:76]   req_dir
 *   [79:78]   zero
 *   [87:80]   epoch
 *   [103:88]  evt_seq
 */
void spf_tandem_fifo_unpack(const uint32_t w[4], spf_tandem_record_t *out)
{
	if (w == NULL || out == NULL)
		return;
	memset(out, 0, sizeof(*out));
	out->sample_counter = ((uint64_t)w[1] << 32) | w[0];
	out->gain_index = (uint8_t)(w[2] & 0xFFu);
	out->reason     = (uint8_t)((w[2] >> 8) & 0x0Fu);
	out->direction  = (uint8_t)((w[2] >> 12) & 0x03u);
	out->epoch      = (uint8_t)((w[2] >> 16) & 0xFFu);
	/* the sequence straddles the word boundary: [103:88] is the top 16 bits
	 * of the record, so bits [31:24] of w[2] and bits [7:0] of w[3] */
	out->sequence   = (uint32_t)(((w[2] >> 24) & 0xFFu) | ((w[3] & 0xFFu) << 8));
}

int spf_tandem_fifo_drain(spf_tandem_reg_read_fn read, void *ctx,
                          spf_tandem_record_t *out, unsigned max,
                          uint32_t *overflow)
{
	uint32_t level = 0;
	unsigned i;
	int n = 0;

	if (read == NULL || out == NULL)
		return -1;
	if (overflow != NULL)
		*overflow = 0;

	if (read(ctx, SPF_TANDEM_REG_EVT_LEVEL, &level) != 0)
		return -1;
	if (overflow != NULL && read(ctx, SPF_TANDEM_REG_EVT_OVF, overflow) != 0)
		return -1;

	/*
	 * Bound by the level read once, not by "until empty". The controller can
	 * push while this runs, so an until-empty loop has no bound at all -- and
	 * this executes on the capture thread, where an unbounded loop is a stall
	 * rather than a slowdown.
	 */
	if (level > max)
		level = max;

	for (i = 0; i < level; i++) {
		uint32_t w[4];
		/* order matters: EVT_HI3 pops, so it must be read last */
		if (read(ctx, SPF_TANDEM_REG_EVT_LO0, &w[0]) != 0 ||
		    read(ctx, SPF_TANDEM_REG_EVT_LO1, &w[1]) != 0 ||
		    read(ctx, SPF_TANDEM_REG_EVT_HI2, &w[2]) != 0 ||
		    read(ctx, SPF_TANDEM_REG_EVT_HI3, &w[3]) != 0)
			return n > 0 ? n : -1;
		spf_tandem_fifo_unpack(w, &out[n]);
		n++;
	}
	return n;
}
