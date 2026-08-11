/*
 * spf-gainctl -- operator control for the tandem AGC.
 *
 *   spf-gainctl status
 *   spf-gainctl mode legacy [--restore slow_attack]
 *   spf-gainctl mode tandem-hold --initial-gain 40
 *   spf-gainctl mode tandem-auto --initial-gain 40
 *   spf-gainctl check-sync
 *
 * §5.7 asks for machine-readable status and a small, stable surface. Status is
 * JSON on stdout; every failure prints which step failed and why, because a
 * transaction that aborts halfway is only useful if it says where.
 *
 * The command layer is deliberately thin: everything it does goes through
 * spf_tandem_ctl, which goes through a backend. That is what let §8.4's failure
 * paths be tested without a radio, and it is why this file has no logic worth
 * testing on its own.
 */

#include "spf_tandem_ctl.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifdef SPF_TANDEM_HAVE_IIO
const spf_tandem_backend_t *spf_tandem_iio_backend(const char *uri);
void spf_tandem_iio_release(void);
#else
static const spf_tandem_backend_t *spf_tandem_iio_backend(const char *uri)
{
	(void)uri;
	return NULL;
}
static void spf_tandem_iio_release(void) { }
#endif

static void usage(FILE *f)
{
	fprintf(f,
		"usage: spf-gainctl [--uri URI] <command>\n"
		"\n"
		"  status                       machine-readable state, JSON\n"
		"  mode legacy [--restore M]    disarm and restore gain mode M\n"
		"  mode tandem-hold [--initial-gain N]\n"
		"  mode tandem-auto [--initial-gain N]\n"
		"  check-sync                   compare the FPGA model against the part\n"
		"\n"
		"Enabling requires the ENSM to be RX-active: CTRL_IN edges are ignored\n"
		"otherwise, so a controller armed outside RX silently does nothing.\n"
		"While tandem is armed the AD9361 accepts host gain writes and drops\n"
		"them with a success return, so this tool refuses them itself.\n");
}

int main(int argc, char **argv)
{
	const char *uri = NULL;
	const char *restore = "slow_attack";
	long initial_gain = 40;
	const spf_tandem_backend_t *be;
	spf_tandem_ctl_t ctl;
	spf_tandem_rc_t rc = SPF_TANDEM_OK;
	char buf[768];
	int i, first = 1;

	for (i = 1; i < argc; i++) {
		if (strcmp(argv[i], "--uri") == 0 && i + 1 < argc) {
			uri = argv[++i]; first = i + 1;
		} else if (strcmp(argv[i], "--restore") == 0 && i + 1 < argc) {
			restore = argv[++i];
		} else if (strcmp(argv[i], "--initial-gain") == 0 && i + 1 < argc) {
			initial_gain = strtol(argv[++i], NULL, 0);
		} else if (strcmp(argv[i], "-h") == 0 || strcmp(argv[i], "--help") == 0) {
			usage(stdout);
			return 0;
		} else if (argv[i][0] != '-' && first > i) {
			first = i;
		}
	}
	if (first >= argc) {
		usage(stderr);
		return 2;
	}
	if (initial_gain < 0 || initial_gain > 76) {
		fprintf(stderr, "initial gain %ld is outside the 0..76 table range\n",
		        initial_gain);
		return 2;
	}

	be = spf_tandem_iio_backend(uri);
	if (be == NULL) {
		fprintf(stderr,
			"no iio backend: this build has no libiio support, or the context "
			"could not be opened.\nResolve radios by serial, never by IP.\n");
		return 3;
	}
	spf_tandem_ctl_init(&ctl, be, (uint8_t)initial_gain);

	if (strcmp(argv[first], "status") == 0) {
		if (spf_tandem_ctl_status(&ctl, buf, sizeof(buf)) < 0) {
			fprintf(stderr, "status unavailable\n");
			spf_tandem_iio_release();
			return 1;
		}
		printf("%s\n", buf);
	} else if (strcmp(argv[first], "check-sync") == 0) {
		rc = spf_tandem_ctl_check_sync(&ctl);
	} else if (strcmp(argv[first], "mode") == 0 && first + 1 < argc) {
		const char *m = argv[first + 1];
		if (strcmp(m, "legacy") == 0)
			rc = spf_tandem_ctl_disable(&ctl, restore);
		else if (strcmp(m, "tandem-hold") == 0)
			rc = spf_tandem_ctl_enable(&ctl, false);
		else if (strcmp(m, "tandem-auto") == 0)
			rc = spf_tandem_ctl_enable(&ctl, true);
		else {
			fprintf(stderr, "unknown mode '%s'\n", m);
			spf_tandem_iio_release();
			return 2;
		}
	} else {
		usage(stderr);
		spf_tandem_iio_release();
		return 2;
	}

	if (rc != SPF_TANDEM_OK) {
		fprintf(stderr, "%s: %s\n", spf_tandem_rc_name(rc),
		        ctl.last_error_detail[0] ? ctl.last_error_detail : "(no detail)");
		if (spf_tandem_ctl_status(&ctl, buf, sizeof(buf)) > 0)
			fprintf(stderr, "%s\n", buf);
		spf_tandem_iio_release();
		return 1;
	}
	spf_tandem_iio_release();
	return 0;
}
