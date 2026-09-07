// SPDX-License-Identifier: GPL-2.0-or-later
//
// Cleanup-baseline-aware continuous monitor for 15/30/60 MS/s acquisition.
//
// The immutable v2 runner remains the 15 MS/s release evidence.  This DNM
// revision retains its observation-relative fault policy and emits an honest
// multirate schema with both canonical and source-center indexes.

#define STARLINK_PSS_MONITOR_V2_NO_MAIN
#include "starlink_pss_acqctl_monitor_v2.c"

static bool monitor_v3_rate(const struct pss_map_info *info,
	uint32_t *rate, uint32_t *factor)
{
	uint32_t selected;

	if (!info)
		return false;
	selected = input_rate_msps(info);
	if (selected != 15U && selected != 30U && selected != 60U)
		return false;
	if (rate)
		*rate = selected;
	if (factor)
		*factor = selected / 15U;
	return true;
}

static bool project_source_center(uint64_t canonical, uint32_t factor,
	uint64_t *source)
{
	if (!source || !factor || canonical > UINT64_MAX / factor)
		return false;
	*source = canonical * factor;
	return true;
}

static int print_monitor_map_v3(const char *serial, uint32_t sequence,
	const struct pss_map_copy *copy,
	const struct pss_acquisition_candidate *candidate,
	const struct monitor_epoch_baseline *baseline,
	uint32_t rate, uint32_t factor)
{
	uint64_t map_source, candidate_canonical = 0U, candidate_source = 0U;

	if (!project_source_center(copy->start_index, factor, &map_source))
		return -1;
	if (candidate) {
		if (candidate->reference_start_index > UINT64_MAX -
			candidate->phase_bin)
			return -1;
		candidate_canonical = candidate->reference_start_index +
			candidate->phase_bin;
		if (!project_source_center(candidate_canonical, factor,
				&candidate_source))
			return -1;
	}

	printf("{\"schema\":\"starlink-pss-acqctl.monitor-map.v2\"," 
	       "\"claim_scope\":\"continuous_multirate_map_transport_only\"," 
	       "\"serial\":\"%s\",\"sequence\":%" PRIu32
	       ",\"input_rate_msps\":%" PRIu32
	       ",\"canonical_rate_msps\":15,\"decimation_factor\":%" PRIu32
	       ",\"bank\":%u,\"generation\":%" PRIu32
	       ",\"start_index_canonical\":%" PRIu64
	       ",\"start_index_source_center\":%" PRIu64
	       ",\"accepted_scores\":%" PRIu32
	       ",\"published_maps\":%" PRIu32
	       ",\"health_flags\":\"0x%08" PRIx32 "\"," 
	       "\"fault_free_epoch\":%s,\"candidate_available\":%s",
	       serial, sequence, rate, factor, copy->bank, copy->generation,
	       copy->start_index, map_source, copy->after.accepted_score_count,
	       copy->after.map_publish_count, copy->after.health_flags,
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
		printf(",\"estimated_frame_period_source_samples\":");
		print_double_or_null(candidate->estimated_frame_period_samples *
			factor);
		printf(",\"candidate_start_index_canonical\":%" PRIu64
		       ",\"candidate_start_index_source_center\":%" PRIu64,
		       candidate_canonical, candidate_source);
	}
	printf(",\"threshold_decision\":null,\"pss_detected\":false,"
	       "\"frame_lock_claim\":false}\n");
	return fflush(stdout) < 0 ? -1 : 0;
}

static void print_monitor_summary_v3(const char *serial,
	unsigned int requested_duration_ms, uint64_t observed_duration_ms,
	uint32_t maps_copied, uint32_t candidate_windows,
	uint32_t first_generation, uint64_t first_start_index,
	const struct pss_map_copy *last_copy,
	const struct pss_map_snapshot *initial_snapshot,
	const struct pss_map_snapshot *post_loop_snapshot,
	const struct ddc_counters *ddc_before,
	const struct ddc_counters *ddc_after,
	const struct monitor_epoch_baseline *baseline,
	uint32_t rate, uint32_t factor)
{
	const struct pss_map_snapshot *cutoff = &last_copy->after;
	uint64_t first_source = 0U, last_source = 0U;

	(void)project_source_center(first_start_index, factor, &first_source);
	(void)project_source_center(last_copy->start_index, factor, &last_source);
	printf("{\"schema\":\"starlink-pss-acqctl.monitor-summary.v2\"," 
	       "\"claim_scope\":\"continuous_multirate_map_transport_only\"," 
	       "\"serial\":\"%s\",\"input_rate_msps\":%" PRIu32
	       ",\"canonical_rate_msps\":15,\"decimation_factor\":%" PRIu32
	       ",\"duration_requested_ms\":%u"
	       ",\"duration_observed_ms\":%" PRIu64
	       ",\"maps_copied\":%" PRIu32
	       ",\"candidate_windows\":%" PRIu32
	       ",\"first_generation\":%" PRIu32
	       ",\"last_generation\":%" PRIu32
	       ",\"first_start_index_canonical\":%" PRIu64
	       ",\"last_start_index_canonical\":%" PRIu64
	       ",\"first_start_index_source_center\":%" PRIu64
	       ",\"last_start_index_source_center\":%" PRIu64
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
	       "\"post_loop_fault_free\":%s,\"threshold_decision\":null,"
	       "\"pss_detected\":false,\"frame_lock_claim\":false}\n",
	       serial, rate, factor, requested_duration_ms, observed_duration_ms,
	       maps_copied, candidate_windows, first_generation,
	       last_copy->generation, first_start_index, last_copy->start_index,
	       first_source, last_source, initial_snapshot->accepted_score_count,
	       cutoff->accepted_score_count,
	       cutoff->accepted_score_count - initial_snapshot->accepted_score_count,
	       initial_snapshot->map_publish_count, cutoff->map_publish_count,
	       cutoff->map_publish_count - initial_snapshot->map_publish_count,
	       post_loop_snapshot->map_publish_count,
	       post_loop_snapshot->ready_mask,
	       observation_delta(cutoff->discarded_score_count,
		baseline->snapshot.discarded_score_count),
	       observation_delta(cutoff->discontinuity_abort_count,
		baseline->snapshot.discontinuity_abort_count),
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

static int run_monitor_v3(const char *serial, const struct pss_map_io *io,
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
	uint64_t first_start_index = 0U, projected = 0U;
	uint32_t maps_copied = 0U, candidate_windows = 0U;
	uint32_t first_generation = 0U, rate = 0U, factor = 0U;
	bool enabled = false;
	int result = -1;

	if (!monitor_v3_rate(info, &rate, &factor)) {
		snprintf(error, error_size,
			"monitor v3 requires a 15, 30, or 60 MS/s contract");
		return -1;
	}
	if (info->status & PSS_MAP_STATUS_ENABLED) {
		snprintf(error, error_size,
			"monitor v3 requires the acquisition engine to be disabled");
		return -1;
	}
	storage = calloc(PSS_ACQUISITION_WINDOW_MAPS * PSS_MAP_PHASE_BINS,
		sizeof(*storage));
	incoming = calloc(PSS_MAP_PHASE_BINS, sizeof(*incoming));
	scratch = calloc(PSS_ACQUISITION_SCRATCH_WORDS, sizeof(*scratch));
	if (!storage || !incoming || !scratch) {
		snprintf(error, error_size, "cannot allocate fixed monitor-v3 buffers");
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
			"cannot establish one clean monitor-v3 observation");
		goto done;
	}
	baseline.snapshot = initial_snapshot;
	if (ddc_before.discontinuity || ddc_before.saturation) {
		snprintf(error, error_size,
			"DDC fault counters were nonzero before monitor-v3 start");
		goto done;
	}
	fprintf(stderr,
		"monitor-v3 rate=%" PRIu32 " inherited shutdown baseline: "
		"discarded=%" PRIu32 " discontinuity_aborts=%" PRIu32 "\n",
		rate, baseline.snapshot.discarded_score_count,
		baseline.snapshot.discontinuity_abort_count);
	if (setvbuf(stdout, NULL, _IOLBF, 0) != 0) {
		snprintf(error, error_size,
			"cannot enable line-buffered monitor-v3 output");
		goto done;
	}

	for (;;) {
		const struct pss_acquisition_candidate *published_candidate = NULL;

		if (interrupted) {
			snprintf(error, error_size, "continuous monitor-v3 interrupted");
			goto done;
		}
		if (pss_map_wait_copy(io, incoming, PSS_MAP_PHASE_BINS,
				&current_copy, timeout_ms, error, error_size) < 0)
			goto done;
		if (!observation_fault_free(&baseline, &current_copy.before) ||
		    !observation_fault_free(&baseline, &current_copy.after)) {
			snprintf(error, error_size,
				"monitor-v3 observation fault counters changed");
			goto done;
		}
		if (maps_copied && !pss_map_copies_contiguous(&previous_copy,
				&current_copy)) {
			snprintf(error, error_size,
				"continuous monitor-v3 maps were not contiguous");
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
		if (print_monitor_map_v3(serial, maps_copied, &current_copy,
				published_candidate, &baseline, rate, factor) < 0) {
			snprintf(error, error_size, "cannot write monitor-v3 output");
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
			"cannot capture final monitor-v3 counters");
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
	    !project_source_center(first_start_index, factor, &projected) ||
	    !project_source_center(previous_copy.start_index, factor, &projected) ||
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
	    ddc_after.discontinuity || ddc_after.saturation ||
	    (rate > 15U &&
	     (ddc_after.accepted == UINT32_MAX || ddc_after.emitted == UINT32_MAX ||
	      ddc_after.accepted <= ddc_before.accepted ||
	      ddc_after.emitted <= ddc_before.emitted))) {
		snprintf(error, error_size,
			"monitor-v3 final continuity or counter gate failed");
		goto done;
	}
	if (pss_map_set_enabled(io, false, true, error, error_size) < 0)
		goto done;
	enabled = false;
	print_monitor_summary_v3(serial, duration_ms, now_ms - started_ms,
		maps_copied, candidate_windows, first_generation,
		first_start_index, &previous_copy, &initial_snapshot,
		&final_snapshot, &ddc_before, &ddc_after, &baseline, rate, factor);
	if (fflush(stdout) < 0) {
		snprintf(error, error_size, "cannot flush monitor-v3 summary");
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
				fprintf(stderr, "monitor-v3 cleanup failed: %s\n",
					cleanup_error);
			else
				fprintf(stderr,
					"monitor-v3 cleanup required direct disable/flush fallback: %s\n",
					cleanup_error);
			result = -1;
		}
	}
	free(scratch);
	free(incoming);
	free(storage);
	return result;
}

static void usage_v3(FILE *stream)
{
	fprintf(stream,
		"usage: starlink_pss_acqctl_monitor_v3 --expect-serial SERIAL "
		"[--devmem PATH] monitor [--duration-ms N] [--timeout-ms N]\n");
}

#ifndef STARLINK_PSS_MONITOR_V3_NO_MAIN
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
	(void)run_monitor_v2;
	(void)usage_v2;

	while (argument < argc && argv[argument][0] == '-') {
		if (!strcmp(argv[argument], "--expect-serial")) {
			if (option_value(argc, argv, &argument, &expected_serial) < 0)
				return EXIT_FAILURE;
		} else if (!strcmp(argv[argument], "--devmem")) {
			if (option_value(argc, argv, &argument, &devmem) < 0)
				return EXIT_FAILURE;
		} else if (!strcmp(argv[argument], "--help")) {
			usage_v3(stdout);
			return EXIT_SUCCESS;
		} else {
			usage_v3(stderr);
			return EXIT_FAILURE;
		}
		++argument;
	}
	if (argument >= argc || strcmp(argv[argument], "monitor"))
		return starlink_pss_acqctl_v1_main(argc, argv);
	argument++;
	while (argument < argc) {
		const char *value;

		if (!strcmp(argv[argument], "--timeout-ms")) {
			if (option_value(argc, argv, &argument, &value) < 0 ||
			    parse_timeout(value, &timeout_ms) < 0) {
				fprintf(stderr, "invalid monitor-v3 timeout option\n");
				return EXIT_FAILURE;
			}
		} else if (!strcmp(argv[argument], "--duration-ms")) {
			if (option_value(argc, argv, &argument, &value) < 0 ||
			    parse_monitor_duration(value, &duration_ms) < 0) {
				fprintf(stderr, "invalid monitor-v3 duration option\n");
				return EXIT_FAILURE;
			}
		} else {
			fprintf(stderr, "invalid monitor-v3 option\n");
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
	if (run_monitor_v3(expected_serial, &io, &info, duration_ms, timeout_ms,
			error, sizeof(error)) < 0) {
		fprintf(stderr, "continuous monitor-v3 failed: %s\n", error);
		goto done;
	}
	return_code = EXIT_SUCCESS;

done:
	unmap_mmio(&mmio);
	return return_code;
}
#endif
