/*
 * spf_tandem_fifo.h
 *
 * Reading the FPGA event FIFO into the records spf_tandem_drain expects.
 *
 * The block exposes one record through four 32-bit windows. Reading the LAST
 * of them (EVT_HI3) is what pops the FIFO -- so the read order is not a style
 * choice, it is the protocol, and reading EVT_HI3 first would discard three
 * quarters of every record. §8 of the design contract fixes the order.
 */

#ifndef SPF_TANDEM_FIFO_H
#define SPF_TANDEM_FIFO_H

#include "spf_tandem_event.h"

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define SPF_TANDEM_REG_EVT_LO0   0x30u
#define SPF_TANDEM_REG_EVT_LO1   0x34u
#define SPF_TANDEM_REG_EVT_HI2   0x38u
#define SPF_TANDEM_REG_EVT_HI3   0x3Cu   /* reading this pops */
#define SPF_TANDEM_REG_EVT_LEVEL 0x40u
#define SPF_TANDEM_REG_EVT_OVF   0x44u

typedef int (*spf_tandem_reg_read_fn)(void *ctx, uint8_t addr, uint32_t *out);

/*
 * Drain up to `max` records. Returns the count, or <0 on a register-read
 * failure. `overflow` receives the block's saturating drop count.
 *
 * Bounded by the level register read once at entry, never by "read until
 * empty": the controller can push while this runs, and an unbounded loop in a
 * capture thread is how a drain becomes a stall.
 */
int spf_tandem_fifo_drain(spf_tandem_reg_read_fn read, void *ctx,
                          spf_tandem_record_t *out, unsigned max,
                          uint32_t *overflow);

/*
 * Register access by mapping the block's page. The base address is fixed by
 * the block design (0x7C450000); open verifies the ID register before
 * returning, so a bitstream without the block fails closed rather than
 * decoding another peripheral as gain events. Returns NULL on failure.
 */
void *spf_tandem_regs_open(void);
void  spf_tandem_regs_close(void *ctx);
int   spf_tandem_reg_read(void *ctx, uint8_t addr, uint32_t *out);
int   spf_tandem_reg_write(void *ctx, uint8_t addr, uint32_t value);

/* exposed for the unit test: turn four register words into a record */
void spf_tandem_fifo_unpack(const uint32_t w[4], spf_tandem_record_t *out);

#endif /* SPF_TANDEM_FIFO_H */
