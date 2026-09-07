// SPDX-License-Identifier: GPL-2.0-or-later

#define STARLINK_PSS_MONITOR_V2_NO_MAIN
#include "starlink_pss_acqctl_monitor_v2.c"

#define CHECK(condition, message) do { \
	if (!(condition)) { \
		fprintf(stderr, "FAIL: %s\n", message); \
		return 1; \
	} \
} while (0)

int main(void)
{
	struct monitor_epoch_baseline baseline = {0};
	struct pss_map_snapshot current = {0};
	(void)run_monitor_v2;
	(void)usage_v2;

	baseline.snapshot.abi_version = PSS_MAP_VERSION_1_1;
	baseline.snapshot.discontinuity_abort_count = 1U;
	current = baseline.snapshot;
	CHECK(cleanup_only_baseline(&baseline.snapshot),
		"one inherited shutdown abort was rejected");
	CHECK(observation_fault_free(&baseline, &current),
		"unchanged inherited shutdown baseline was rejected");
	CHECK(observation_delta(1U, 1U) == 0U,
		"shutdown baseline did not normalize to zero");

	current.discontinuity_abort_count++;
	CHECK(!observation_fault_free(&baseline, &current),
		"a new in-observation abort was accepted");
	current = baseline.snapshot;
	current.discarded_score_count++;
	CHECK(!observation_fault_free(&baseline, &current),
		"a new discarded score was accepted");
	current = baseline.snapshot;
	current.scheduler_gap_count = 1U;
	CHECK(!observation_fault_free(&baseline, &current),
		"a new scheduler fault was accepted");
	current = baseline.snapshot;
	current.health_flags = 1U << 4;
	CHECK(!observation_fault_free(&baseline, &current),
		"a new sticky detector fault was accepted");
	current = baseline.snapshot;
	current.ready_mask = 1U;
	CHECK(observation_fault_free(&baseline, &current),
		"a completed map made an otherwise clean observation fail");

	baseline.snapshot.ready_mask = 1U;
	CHECK(!cleanup_only_baseline(&baseline.snapshot),
		"a stale ready map was accepted as a fresh baseline");
	baseline.snapshot.ready_mask = 0U;
	baseline.snapshot.map_overrun_count = 1U;
	CHECK(!cleanup_only_baseline(&baseline.snapshot),
		"an inherited map overrun was accepted");
	baseline.snapshot.map_overrun_count = 0U;
	baseline.snapshot.discontinuity_abort_count = UINT32_MAX;
	CHECK(!cleanup_only_baseline(&baseline.snapshot),
		"a saturated shutdown counter was accepted");

	puts("STARLINK_PSS_MONITOR_V2_PASS cases=10");
	return 0;
}
