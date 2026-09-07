// SPDX-License-Identifier: GPL-2.0-or-later
//
// Back-to-back monitor runner for the immutable PSMA 1.1 FPGA image.
//
// PSMA 1.1 keeps phase-map counters until PL reset.  A successful monitor
// deliberately disables acquisition after its cutoff snapshot; if a partial
// map is active, that shutdown increments discontinuity_abort_count.  The v1
// runner consequently cannot open a second observation even though every
// in-observation health counter is clean.  This version treats the two
// shutdown-only phase-map counters as an inherited baseline, requires every
// other fault field to be zero, and requires the complete baseline to remain
// unchanged throughout the new observation.  Output remains the v1 NDJSON
// transport schema because its fault fields describe the bounded observation.

#define main starlink_pss_acqctl_v1_main
#define run_monitor run_monitor_v1
#include "starlink_pss_acqctl.c"
#undef run_monitor
#undef main

struct monitor_epoch_baseline {
	struct pss_map_snapshot snapshot;
};

static bool cleanup_only_baseline(const struct pss_map_snapshot *snapshot)
{
	return snapshot && !snapshot->ready_mask &&
		snapshot->discarded_score_count != UINT32_MAX &&
		snapshot->discontinuity_abort_count != UINT32_MAX &&
		!snapshot->health_flags && !snapshot->map_overrun_count &&
		!snapshot->score_protocol_error_count &&
		!snapshot->arithmetic_overflow_count &&
		!snapshot->map_read_error_count &&
		!snapshot->map_release_error_count &&
		!snapshot->ingress_dropped_sample_count &&
		!snapshot->scheduler_gap_count &&
		!snapshot->scheduler_index_error_count &&
		!snapshot->scheduler_overflow_count &&
		!snapshot->detector_fault_count &&
		!snapshot->score_phase_index_discontinuity_count &&
		!snapshot->score_denominator_zero_count;
}

static bool observation_fault_free(
	const struct monitor_epoch_baseline *baseline,
	const struct pss_map_snapshot *snapshot)
{
	const struct pss_map_snapshot *base;

	if (!baseline || !snapshot)
		return false;
	base = &baseline->snapshot;
	return cleanup_only_baseline(base) &&
		snapshot->abi_version == base->abi_version &&
		snapshot->discarded_score_count == base->discarded_score_count &&
		snapshot->discontinuity_abort_count ==
			base->discontinuity_abort_count &&
		snapshot->map_overrun_count == base->map_overrun_count &&
		snapshot->score_protocol_error_count ==
			base->score_protocol_error_count &&
		snapshot->arithmetic_overflow_count ==
			base->arithmetic_overflow_count &&
		snapshot->map_read_error_count == base->map_read_error_count &&
		snapshot->map_release_error_count == base->map_release_error_count &&
		snapshot->health_flags == base->health_flags &&
		snapshot->ingress_dropped_sample_count ==
			base->ingress_dropped_sample_count &&
		snapshot->scheduler_gap_count == base->scheduler_gap_count &&
		snapshot->scheduler_index_error_count ==
			base->scheduler_index_error_count &&
		snapshot->scheduler_overflow_count ==
			base->scheduler_overflow_count &&
		snapshot->detector_fault_count == base->detector_fault_count &&
		snapshot->score_phase_index_discontinuity_count ==
			base->score_phase_index_discontinuity_count &&
		snapshot->score_denominator_zero_count ==
			base->score_denominator_zero_count;
}

static uint32_t observation_delta(uint32_t value, uint32_t baseline)
{
	return value >= baseline ? value - baseline : UINT32_MAX;
}

static int print_monitor_map_v2(const char *serial, uint32_t sequence,
	const struct pss_map_copy *copy,
	const struct pss_acquisition_candidate *candidate,
	const struct monitor_epoch_baseline *baseline)
{
	printf("{\"schema\":\"starlink-pss-acqctl.monitor-map.v1\","
	       "\"claim_scope\":\"continuous_map_transport_only\","
	       "\"serial\":\"%s\",\"sequence\":%" PRIu32
	       ",\"bank\":%u,\"generation\":%" PRIu32
	       ",\"start_index_canonical\":%" PRIu64
	       ",\"accepted_scores\":%" PRIu32
	       ",\"published_maps\":%" PRIu32
	       ",\"health_flags\":\"0x%08" PRIx32 "\","
	       "\"fault_free_epoch\":%s,\"candidate_available\":%s",
	       serial, sequence, copy->bank, copy->generation, copy->start_index,
	       copy->after.accepted_score_count, copy->after.map_publish_count,
	       copy->after.health_flags,
	       observation_fault_free(baseline, &copy->after) ? "true" : "false",
	       candidate ? "true" : "false");
	if (candidate) {
		printf(",\"phase_bin\":%" PRIu32
		       ",\"drift_bins_per_64_frames\":%" PRId32
		       ",\"combined_score\":%" PRIu32
		       ",\"combined_median\":",
		       candidate->phase_bin, candidate->drift_bins_per_tile,
		       candidate->combined_score);
		print_double_or_null(candidate->combined_median);
		printf(",\"peak_to_median\":");
		print_double_or_null(candidate->peak_to_median);
		printf(",\"robust_z\":");
		print_double_or_null(candidate->robust_z);
		printf(",\"estimated_frame_period_canonical_samples\":");
		print_double_or_null(candidate->estimated_frame_period_samples);
	}
	printf(",\"threshold_decision\":null,\"pss_detected\":false,"
	       "\"frame_lock_claim\":false}\n");
	return fflush(stdout) < 0 ? -1 : 0;
}

static void print_monitor_summary_v2(const char *serial,
	unsigned int requested_duration_ms, uint64_t observed_duration_ms,
	uint32_t maps_copied, uint32_t candidate_windows,
	uint32_t first_generation, uint64_t first_start_index,
	const struct pss_map_copy *last_copy,
	const struct pss_map_snapshot *initial_snapshot,
	const struct pss_map_snapshot *post_loop_snapshot,
	const struct ddc_counters *ddc_before,
	const struct ddc_counters *ddc_after,
	const struct monitor_epoch_baseline *baseline)
{
	const struct pss_map_snapshot *cutoff = &last_copy->after;
	const struct pss_map_snapshot *base = &baseline->snapshot;

	printf("{\"schema\":\"starlink-pss-acqctl.monitor-summary.v1\","
	       "\"claim_scope\":\"continuous_map_transport_only\","
	       "\"serial\":\"%s\",\"input_rate_msps\":15,"
	       "\"canonical_rate_msps\":15,"
	       "\"duration_requested_ms\":%u,"
	       "\"duration_observed_ms\":%" PRIu64
	       ",\"maps_copied\":%" PRIu32
	       ",\"candidate_windows\":%" PRIu32
	       ",\"first_generation\":%" PRIu32
	       ",\"last_generation\":%" PRIu32
	       ",\"first_start_index_canonical\":%" PRIu64
	       ",\"last_start_index_canonical\":%" PRIu64
	       ",\"accepted_scores_before\":%" PRIu32
	       ",\"accepted_scores_at_cutoff\":%" PRIu32
	       ",\"accepted_scores_delta\":%" PRIu32
	       ",\"published_maps_before\":%" PRIu32
	       ",\"published_maps_at_cutoff\":%" PRIu32
	       ",\"published_maps_delta\":%" PRIu32
	       ",\"post_loop_published_maps\":%" PRIu32
	       ",\"post_loop_ready_mask\":%" PRIu32
	       ",\"discarded_scores_at_cutoff\":%" PRIu32
	       ",\"discontinuity_aborts_at_cutoff\":%" PRIu32
	       ",\"map_overruns_at_cutoff\":%" PRIu32
	       ",\"score_protocol_errors_at_cutoff\":%" PRIu32
	       ",\"arithmetic_overflows_at_cutoff\":%" PRIu32
	       ",\"map_read_errors_at_cutoff\":%" PRIu32
	       ",\"map_release_errors_at_cutoff\":%" PRIu32
	       ",\"ingress_dropped_at_cutoff\":%" PRIu32
	       ",\"scheduler_gaps_at_cutoff\":%" PRIu32
	       ",\"scheduler_index_errors_at_cutoff\":%" PRIu32
	       ",\"scheduler_overflows_at_cutoff\":%" PRIu32
	       ",\"detector_faults_at_cutoff\":%" PRIu32
	       ",\"phase_discontinuities_at_cutoff\":%" PRIu32
	       ",\"denominator_zero_at_cutoff\":%" PRIu32
	       ",\"ingress_fifo_level_at_cutoff\":%u"
	       ",\"ingress_fifo_maximum_at_cutoff\":%u"
	       ",\"candidate_fifo_level_at_cutoff\":%u"
	       ",\"candidate_fifo_maximum_at_cutoff\":%u"
	       ",\"health_flags_at_cutoff\":\"0x%08" PRIx32 "\","
	       "\"ddc_accepted_before\":%" PRIu32
	       ",\"ddc_accepted_after\":%" PRIu32
	       ",\"ddc_emitted_before\":%" PRIu32
	       ",\"ddc_emitted_after\":%" PRIu32
	       ",\"ddc_discontinuity_after\":%" PRIu32
	       ",\"ddc_saturation_after\":%" PRIu32
	       ",\"continuity_ok\":true,\"fault_free_epoch\":%s,"
	       "\"post_loop_fault_free\":%s,"
	       "\"threshold_decision\":null,\"pss_detected\":false,"
	       "\"frame_lock_claim\":false}\n",
	       serial, requested_duration_ms, observed_duration_ms, maps_copied,
	       candidate_windows, first_generation, last_copy->generation,
	       first_start_index, last_copy->start_index,
	       initial_snapshot->accepted_score_count,
	       cutoff->accepted_score_count,
	       cutoff->accepted_score_count - initial_snapshot->accepted_score_count,
	       initial_snapshot->map_publish_count,
	       cutoff->map_publish_count,
	       cutoff->map_publish_count - initial_snapshot->map_publish_count,
	       post_loop_snapshot->map_publish_count, post_loop_snapshot->ready_mask,
	       observation_delta(cutoff->discarded_score_count,
		base->discarded_score_count),
	       observation_delta(cutoff->discontinuity_abort_count,
		base->discontinuity_abort_count),
	       cutoff->map_overrun_count, cutoff->score_protocol_error_count,
	       cutoff->arithmetic_overflow_count, cutoff->map_read_error_count,
	       cutoff->map_release_error_count,
	       cutoff->ingress_dropped_sample_count, cutoff->scheduler_gap_count,
	       cutoff->scheduler_index_error_count,
	       cutoff->scheduler_overflow_count, cutoff->detector_fault_count,
	       cutoff->score_phase_index_discontinuity_count,
	       cutoff->score_denominator_zero_count, cutoff->ingress_fifo_level,
	       cutoff->ingress_maximum_fifo_level,
	       cutoff->candidate_fifo_stored_count,
	       cutoff->candidate_fifo_maximum_stored_count, cutoff->health_flags,
	       ddc_before->accepted, ddc_after->accepted,
	       ddc_before->emitted, ddc_after->emitted,
	       ddc_after->discontinuity, ddc_after->saturation,
	       observation_fault_free(baseline, cutoff) ? "true" : "false",
	       observation_fault_free(baseline, post_loop_snapshot) ?
		"true" : "false");
}

static int run_monitor_v2(const char *serial, const struct pss_map_io *io,
	const struct pss_map_info *info, unsigned int duration_ms,
	unsigned int timeout_ms, char *error, size_t error_size)
{
	uint16_t *storage = NULL, *incoming = NULL;
	uint32_t *scratch = NULL;
	struct pss_map_window window;
	struct pss_map_copy previous_copy, current_copy;
	struct pss_map_snapshot initial_snapshot, final_snapshot;
	struct pss_acquisition_candidate candidate;
	struct monitor_epoch_baseline baseline;
	struct ddc_counters ddc_before = {0}, ddc_after = {0};
	uint64_t started_ms, now_ms;
	uint64_t first_start_index = 0U;
	uint32_t maps_copied = 0U, candidate_windows = 0U;
	uint32_t first_generation = 0U;
	bool enabled = false;
	int result = -1;

	if (input_rate_msps(info) != 15U) {
		snprintf(error, error_size,
			"monitor v2 qualifies only the canonical 15 MS/s input");
		return -1;
	}
	if (info->status & PSS_MAP_STATUS_ENABLED) {
		snprintf(error, error_size,
			"monitor v2 requires the acquisition engine to be disabled");
		return -1;
	}
	storage = calloc(PSS_ACQUISITION_WINDOW_MAPS * PSS_MAP_PHASE_BINS,
		sizeof(*storage));
	incoming = calloc(PSS_MAP_PHASE_BINS, sizeof(*incoming));
	scratch = calloc(PSS_ACQUISITION_SCRATCH_WORDS, sizeof(*scratch));
	if (!storage || !incoming || !scratch) {
		snprintf(error, error_size, "cannot allocate fixed monitor buffers");
		goto done;
	}
	if (pss_map_window_init(&window, storage,
		PSS_ACQUISITION_WINDOW_MAPS * PSS_MAP_PHASE_BINS,
		PSS_MAP_PHASE_BINS, PSS_MAP_TILE_FRAMES,
		error, error_size) < 0 ||
	    pss_map_set_enabled(io, true, true, error, error_size) < 0)
		goto done;
	enabled = true;
	if (pss_map_take_snapshot(io, &initial_snapshot, timeout_ms,
			error, error_size) < 0 ||
	    !cleanup_only_baseline(&initial_snapshot) ||
	    read_ddc_counters(io, &ddc_before) < 0 ||
	    monotonic_milliseconds(&started_ms) < 0) {
		snprintf(error, error_size,
			"cannot establish one clean monitor-v2 observation");
		goto done;
	}
	baseline.snapshot = initial_snapshot;
	if (ddc_before.discontinuity || ddc_before.saturation) {
		snprintf(error, error_size,
			"DDC fault counters were nonzero before monitor-v2 start");
		goto done;
	}
	fprintf(stderr,
		"monitor-v2 inherited shutdown baseline: discarded=%" PRIu32
		" discontinuity_aborts=%" PRIu32 "\n",
		baseline.snapshot.discarded_score_count,
		baseline.snapshot.discontinuity_abort_count);
	if (setvbuf(stdout, NULL, _IOLBF, 0) != 0) {
		snprintf(error, error_size,
			"cannot enable line-buffered monitor-v2 output");
		goto done;
	}

	for (;;) {
		const struct pss_acquisition_candidate *published_candidate = NULL;

		if (interrupted) {
			snprintf(error, error_size, "continuous monitor-v2 interrupted");
			goto done;
		}
		if (pss_map_wait_copy(io, incoming, PSS_MAP_PHASE_BINS,
				&current_copy, timeout_ms, error, error_size) < 0)
			goto done;
		if (!observation_fault_free(&baseline, &current_copy.before) ||
		    !observation_fault_free(&baseline, &current_copy.after)) {
			snprintf(error, error_size,
				"monitor-v2 observation fault counters changed");
			goto done;
		}
		if (maps_copied && !pss_map_copies_contiguous(&previous_copy,
				&current_copy)) {
			snprintf(error, error_size,
				"continuous monitor-v2 maps were not contiguous");
			goto done;
		}
		if (pss_map_window_push(&window, incoming,
				current_copy.generation, current_copy.start_index,
				error, error_size) < 0)
			goto done;
		if (!maps_copied) {
			first_generation = current_copy.generation;
			first_start_index = current_copy.start_index;
		}
		maps_copied++;
		if (pss_map_window_ready(&window)) {
			if (pss_acquisition_extract(&window,
					pss_acquisition_default_drift_bank,
					PSS_ACQUISITION_DRIFT_HYPOTHESES,
					scratch, PSS_ACQUISITION_SCRATCH_WORDS,
					&candidate, error, error_size) < 0)
				goto done;
			published_candidate = &candidate;
			candidate_windows++;
		}
		if (print_monitor_map_v2(serial, maps_copied, &current_copy,
				published_candidate, &baseline) < 0) {
			snprintf(error, error_size, "cannot write monitor-v2 output");
			goto done;
		}
		previous_copy = current_copy;
		if (monotonic_milliseconds(&now_ms) < 0) {
			snprintf(error, error_size, "CLOCK_MONOTONIC read failed");
			goto done;
		}
		if (now_ms - started_ms >= duration_ms)
			break;
	}

	if (pss_map_take_snapshot(io, &final_snapshot, timeout_ms,
			error, error_size) < 0 ||
	    read_ddc_counters(io, &ddc_after) < 0 ||
	    monotonic_milliseconds(&now_ms) < 0) {
		snprintf(error, error_size,
			"cannot capture final monitor-v2 counters");
		goto done;
	}
	if (maps_copied < PSS_ACQUISITION_WINDOW_MAPS ||
	    candidate_windows != maps_copied -
		(PSS_ACQUISITION_WINDOW_MAPS - 1U) ||
	    previous_copy.generation - first_generation != maps_copied - 1U ||
	    first_start_index > UINT64_MAX -
		(uint64_t)(maps_copied - 1U) *
		PSS_MAP_PHASE_BINS * PSS_MAP_TILE_FRAMES ||
	    previous_copy.start_index != first_start_index +
		(uint64_t)(maps_copied - 1U) *
		PSS_MAP_PHASE_BINS * PSS_MAP_TILE_FRAMES ||
	    !observation_fault_free(&baseline, &previous_copy.after) ||
	    !observation_fault_free(&baseline, &final_snapshot) ||
	    previous_copy.after.accepted_score_count == UINT32_MAX ||
	    previous_copy.after.map_publish_count == UINT32_MAX ||
	    previous_copy.after.accepted_score_count <
		initial_snapshot.accepted_score_count ||
	    previous_copy.after.map_publish_count <
		initial_snapshot.map_publish_count ||
	    previous_copy.after.map_publish_count -
		initial_snapshot.map_publish_count != maps_copied ||
	    final_snapshot.accepted_score_count <
		previous_copy.after.accepted_score_count ||
	    final_snapshot.map_publish_count <
		previous_copy.after.map_publish_count ||
	    ddc_after.discontinuity || ddc_after.saturation) {
		snprintf(error, error_size,
			"monitor-v2 final continuity or counter gate failed");
		goto done;
	}
	if (pss_map_set_enabled(io, false, true, error, error_size) < 0)
		goto done;
	enabled = false;
	print_monitor_summary_v2(serial, duration_ms, now_ms - started_ms,
		maps_copied, candidate_windows, first_generation,
		first_start_index, &previous_copy, &initial_snapshot,
		&final_snapshot, &ddc_before, &ddc_after, &baseline);
	if (fflush(stdout) < 0) {
		snprintf(error, error_size, "cannot flush monitor-v2 summary");
		goto done;
	}
	result = 0;

done:
	if (enabled) {
		char cleanup_error[ERROR_SIZE] = {0};

		if (pss_map_set_enabled(io, false, true,
				cleanup_error, sizeof(cleanup_error)) < 0) {
			if (!io->write32 || io->write32(io->context,
					PSS_MAP_REG_CONTROL, 2U) < 0)
				fprintf(stderr, "monitor-v2 cleanup failed: %s\n",
					cleanup_error);
			else
				fprintf(stderr,
					"monitor-v2 cleanup required direct disable/flush fallback: %s\n",
					cleanup_error);
			result = -1;
		}
	}
	free(scratch);
	free(incoming);
	free(storage);
	return result;
}

static void usage_v2(FILE *stream)
{
	fprintf(stream,
		"usage: starlink_pss_acqctl_monitor_v2 --expect-serial SERIAL "
		"[--devmem PATH] monitor [--duration-ms N] [--timeout-ms N]\n");
}

#ifndef STARLINK_PSS_MONITOR_V2_NO_MAIN
int main(int argc, char **argv)
{
	const char *expected_serial = NULL;
	const char *devmem = "/dev/mem";
	struct mapped_mmio mmio = {.fd = -1};
	struct pss_map_io io;
	struct pss_map_info info;
	char error[ERROR_SIZE] = {0};
	unsigned int timeout_ms = DEFAULT_TIMEOUT_MS;
	unsigned int duration_ms = DEFAULT_MONITOR_DURATION_MS;
	int argument = 1;
	int return_code = EXIT_FAILURE;

	while (argument < argc && argv[argument][0] == '-') {
		if (!strcmp(argv[argument], "--expect-serial")) {
			if (option_value(argc, argv, &argument, &expected_serial) < 0)
				return EXIT_FAILURE;
		} else if (!strcmp(argv[argument], "--devmem")) {
			if (option_value(argc, argv, &argument, &devmem) < 0)
				return EXIT_FAILURE;
		} else if (!strcmp(argv[argument], "--help")) {
			usage_v2(stdout);
			return EXIT_SUCCESS;
		} else {
			usage_v2(stderr);
			return EXIT_FAILURE;
		}
		++argument;
	}
	if (argument >= argc)
		return starlink_pss_acqctl_v1_main(argc, argv);
	if (strcmp(argv[argument], "monitor"))
		return starlink_pss_acqctl_v1_main(argc, argv);
	argument++;
	while (argument < argc) {
		const char *value;

		if (!strcmp(argv[argument], "--timeout-ms")) {
			if (option_value(argc, argv, &argument, &value) < 0 ||
			    parse_timeout(value, &timeout_ms) < 0) {
				fprintf(stderr, "invalid monitor-v2 timeout option\n");
				return EXIT_FAILURE;
			}
		} else if (!strcmp(argv[argument], "--duration-ms")) {
			if (option_value(argc, argv, &argument, &value) < 0 ||
			    parse_monitor_duration(value, &duration_ms) < 0) {
				fprintf(stderr, "invalid monitor-v2 duration option\n");
				return EXIT_FAILURE;
			}
		} else {
			fprintf(stderr, "invalid monitor-v2 option\n");
			return EXIT_FAILURE;
		}
		++argument;
	}
	if (verify_local_serial(expected_serial) < 0 ||
	    install_signal_handlers() < 0 || map_mmio(&mmio, devmem) < 0)
		return EXIT_FAILURE;
	io.context = &mmio;
	io.read32 = mapped_read32;
	io.write32 = mapped_write32;
	if (pss_map_require_contract(&io, &info, error, sizeof(error)) < 0) {
		fprintf(stderr, "acquisition contract check failed: %s\n", error);
		goto done;
	}
	if (run_monitor_v2(expected_serial, &io, &info, duration_ms, timeout_ms,
			error, sizeof(error)) < 0) {
		fprintf(stderr, "continuous monitor-v2 failed: %s\n", error);
		goto done;
	}
	return_code = EXIT_SUCCESS;

done:
	unmap_mmio(&mmio);
	return return_code;
}
#endif
