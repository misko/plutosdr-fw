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
		"  --harness-baseline REF       this unit's measured D(g,g) reference\n"
		"\n"
		"Enabling requires the ENSM to be RX-active: CTRL_IN edges are ignored\n"
		"otherwise, so a controller armed outside RX silently does nothing.\n"
		"While tandem is armed the AD9361 accepts host gain writes and drops\n"
		"them with a success return, so this tool refuses them itself.\n"
		"\n"
		"Tandem's phase benefit depends on harness health, not just on the\n"
		"radio. E-GSC6 measured two units whose interaction terms matched to\n"
		"0.05 degrees but whose D(g,g) differed 5-7x by band; on the unit with\n"
		"a damaged connector the high band came in at 0.3x, meaning tandem made\n"
		"phase WORSE than leaving it off. Pass --harness-baseline with this\n"
		"unit's own measured reference, re-measured after any connector work.\n");
}

int main(int argc, char **argv)
{
	const char *uri = NULL;
	const char *restore = "slow_attack";
	const char *harness_baseline = NULL;
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
		} else if (strcmp(argv[i], "--harness-baseline") == 0 && i + 1 < argc) {
			harness_baseline = argv[++i];
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
	/* Range-check only what cannot depend on the part: an index is a 7-bit
	 * field. The real bound is the part's Max Full/LMT Gain Table Index, which
	 * enable reads and enforces (D-8) -- checking against a compiled-in 76
	 * here would reject a valid index on a radio with a longer table and
	 * accept an invalid one on a radio with a shorter table. */
	if (initial_gain < 0 || initial_gain > 127) {
		fprintf(stderr, "initial gain %ld is not a 7-bit gain-table index\n",
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
		else if (strcmp(m, "tandem-hold") == 0 || strcmp(m, "tandem-auto") == 0) {
			/*
			 * Warn rather than refuse. Firmware cannot measure harness health,
			 * so a hard block would be enforcing a condition it cannot check --
			 * and tandem is still the right answer for dynamic range on a unit
			 * whose phase is not being used. But arming silently on an
			 * uncharacterised harness is how a unit ends up 0.3x on the band
			 * that matters most, so this is loud and on stderr.
			 */
			if (harness_baseline == NULL)
				fprintf(stderr,
					"warning: arming tandem with no harness baseline.\n"
					"  Phase benefit is per-unit and per-harness: E-GSC6 measured\n"
					"  0.3x (worse than off) in the high band on a unit with a\n"
					"  damaged connector, against >=7.2x on the control unit.\n"
					"  Pass --harness-baseline with this unit's measured D(g,g).\n");
			else
				fprintf(stderr, "harness baseline: %s\n", harness_baseline);
			rc = spf_tandem_ctl_enable(&ctl, strcmp(m, "tandem-auto") == 0);
		}
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
