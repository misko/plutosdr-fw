/*
 * spf_tandem_iio.c -- the real backend, over libiio.
 *
 * Only compiled when libiio is present (SPF_TANDEM_HAVE_IIO). Everything the
 * control layer needs is here and nowhere else, so the transaction logic stays
 * host-testable against the mock.
 *
 * Two conventions carried from the campaign procedures rather than invented:
 * resolve radios by serial and never by IP, because both units expose a
 * USB-gadget interface on a duplicate 192.168.2.10; and RX channels need the
 * input flag, or a lookup by name silently returns the TX channel of the same
 * name.
 */

#include "spf_tandem_ctl.h"

#include <iio.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

struct iio_ctx {
	struct iio_context *ctx;
	struct iio_device  *phy;     /* ad9361-phy   */
	struct iio_device  *tandem;  /* the FPGA block, by name */
};

static struct iio_ctx g;

static struct iio_channel *rx_chan(struct iio_device *d, int channel)
{
	/* the input flag is required: without it this returns the TX channel */
	return iio_device_find_channel(d, channel == 0 ? "voltage0" : "voltage1", false);
}

static int be_fpga_read(void *v, uint8_t addr, uint32_t *out)
{
	(void)v;
	if (g.tandem == NULL) return -1;
	return iio_device_reg_read(g.tandem, addr, out);
}

static int be_fpga_write(void *v, uint8_t addr, uint32_t val)
{
	(void)v;
	if (g.tandem == NULL) return -1;
	return iio_device_reg_write(g.tandem, addr, val);
}

static int be_ad9361_read(void *v, uint16_t reg, uint8_t *out)
{
	uint32_t tmp = 0;
	int rc;
	(void)v;
	rc = iio_device_reg_read(g.phy, reg, &tmp);
	if (rc == 0) *out = (uint8_t)(tmp & 0xFFu);
	return rc;
}

static int be_ad9361_write(void *v, uint16_t reg, uint8_t val)
{
	(void)v;
	return iio_device_reg_write(g.phy, reg, val);
}

static int be_gain_get(void *v, int channel, uint8_t *index)
{
	struct iio_channel *ch = rx_chan(g.phy, channel);
	uint32_t val = 0;
	int rc;
	(void)v;
	if (ch == NULL) return -1;
	/* the full-table index lives in 0x2B0 / 0x2B5; hardwaregain is dB and is
	 * only a cross-check, because the index-to-dB offset is band dependent */
	rc = iio_device_reg_read(g.phy,
		channel == 0 ? SPF_AD9361_REG_GAIN_RX1 : SPF_AD9361_REG_GAIN_RX2, &val);
	if (rc == 0) *index = (uint8_t)(val & 0x7Fu);
	return rc;
}

static int be_gain_set(void *v, int channel, uint8_t index)
{
	struct iio_channel *ch = rx_chan(g.phy, channel);
	(void)v;
	if (ch == NULL) return -1;
	return (int)iio_channel_attr_write_longlong(ch, "hardwaregain", (long long)index);
}

static int be_mode_set(void *v, int channel, const char *mode)
{
	struct iio_channel *ch = rx_chan(g.phy, channel);
	ssize_t n;
	(void)v;
	if (ch == NULL) return -1;
	n = iio_channel_attr_write(ch, "gain_control_mode", mode);
	return n < 0 ? (int)n : 0;
}

static int be_ensm_get(void *v, char *buf, size_t len)
{
	ssize_t n;
	(void)v;
	n = iio_device_attr_read(g.phy, "ensm_mode", buf, len);
	return n < 0 ? (int)n : 0;
}

static int be_full_gain_table(void *v, bool *full)
{
	uint32_t v2 = 0;
	int rc;
	(void)v;
	/* REG_AGC_CONFIG_2 bit 3 is AGC_USE_FULL_GAIN_TABLE */
	rc = iio_device_reg_read(g.phy, SPF_AD9361_REG_AGC_CONFIG_2, &v2);
	if (rc == 0) *full = (v2 & 0x08u) != 0u;
	return rc;
}

static const spf_tandem_backend_t iio_backend = {
	.ctx = NULL,
	.fpga_read = be_fpga_read,
	.fpga_write = be_fpga_write,
	.ad9361_read = be_ad9361_read,
	.ad9361_write = be_ad9361_write,
	.gain_get = be_gain_get,
	.gain_set = be_gain_set,
	.mode_set = be_mode_set,
	.ensm_get = be_ensm_get,
	.full_gain_table = be_full_gain_table,
};

const spf_tandem_backend_t *spf_tandem_iio_backend(const char *uri)
{
	g.ctx = uri ? iio_create_context_from_uri(uri) : iio_create_default_context();
	if (g.ctx == NULL)
		return NULL;
	g.phy = iio_context_find_device(g.ctx, "ad9361-phy");
	if (g.phy == NULL) {
		iio_context_destroy(g.ctx);
		g.ctx = NULL;
		return NULL;
	}
	/* absent on a build whose bitstream does not carry the block; the control
	 * layer reports that as a missing ID rather than crashing */
	g.tandem = iio_context_find_device(g.ctx, "tandem-agc");
	return &iio_backend;
}

void spf_tandem_iio_release(void)
{
	if (g.ctx != NULL) {
		iio_context_destroy(g.ctx);
		g.ctx = NULL;
	}
}
