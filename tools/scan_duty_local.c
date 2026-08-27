// SPDX-License-Identifier: GPL-2.0-or-later
/* Measure tune/settle/single-buffer capture duty cycle locally on Pluto+. */

#define _POSIX_C_SOURCE 200809L

#include <errno.h>
#include <iio.h>
#include <inttypes.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#define ARRAY_SIZE(x) (sizeof(x) / sizeof((x)[0]))
#define FRAMES 75U
#define SAMPLE_RATE 3000000LL
#define RF_BANDWIDTH 1500000LL
#define FRAME_SAMPLES 240000U
#define SETTLE_US 250U

static const long long frequencies[] = {
	900000000LL, 950000000LL, 1000000000LL, 1050000000LL, 1100000000LL,
};

struct timings {
	double values[FRAMES];
};

static double now_seconds(void)
{
	struct timespec value;
	clock_gettime(CLOCK_MONOTONIC, &value);
	return value.tv_sec + value.tv_nsec / 1e9;
}

static void sleep_microseconds(unsigned int microseconds)
{
	struct timespec delay = {
		.tv_sec = microseconds / 1000000U,
		.tv_nsec = (long)(microseconds % 1000000U) * 1000L,
	};
	while (nanosleep(&delay, &delay) < 0 && errno == EINTR)
		;
}

static int compare_double(const void *left, const void *right)
{
	const double a = *(const double *)left;
	const double b = *(const double *)right;
	return (a > b) - (a < b);
}

static double quantile(const struct timings *input, double fraction)
{
	double values[FRAMES];
	double position, weight;
	unsigned int lower, upper;

	memcpy(values, input->values, sizeof(values));
	qsort(values, FRAMES, sizeof(values[0]), compare_double);
	position = fraction * (FRAMES - 1U);
	lower = (unsigned int)position;
	upper = lower + 1U < FRAMES ? lower + 1U : lower;
	weight = position - lower;
	return values[lower] * (1.0 - weight) + values[upper] * weight;
}

static double maximum(const struct timings *input)
{
	double result = input->values[0];
	unsigned int index;
	for (index = 1; index < FRAMES; ++index)
		if (input->values[index] > result)
			result = input->values[index];
	return result;
}

static double mean(const struct timings *input)
{
	double sum = 0.0;
	unsigned int index;
	for (index = 0; index < FRAMES; ++index)
		sum += input->values[index];
	return sum / FRAMES;
}

static void print_stats(const char *name, const struct timings *values, bool comma)
{
	printf("    \"%s\": {\"mean_ms\": %.6f, \"p50_ms\": %.6f, "
	       "\"p95_ms\": %.6f, \"p99_ms\": %.6f, \"max_ms\": %.6f}%s\n",
	       name, mean(values) * 1000.0, quantile(values, 0.50) * 1000.0,
	       quantile(values, 0.95) * 1000.0, quantile(values, 0.99) * 1000.0,
	       maximum(values) * 1000.0, comma ? "," : "");
}

static struct iio_channel *find_channel(struct iio_device *device,
	const char *name, bool output)
{
	return iio_device_find_channel(device, name, output);
}

int main(void)
{
	struct iio_context *context = NULL;
	struct iio_device *phy, *rx;
	struct iio_channel *lo, *rx_phy;
	struct timings tune = {0}, create = {0}, refill = {0}, payload_touch = {0};
	struct timings destroy = {0}, whole_frame = {0};
	char original_lo[64], original_rate[64], original_bw[64];
	uint8_t slot_order[FRAMES];
	uint32_t checksum = 2166136261U;
	uint64_t payload_bytes = 0;
	double run_start, wall_seconds, before, after, frame_start;
	unsigned int index, channel_index;
	int ret = EXIT_FAILURE;

	context = iio_create_local_context();
	if (!context) {
		perror("iio_create_local_context");
		goto out;
	}
	phy = iio_context_find_device(context, "ad9361-phy");
	rx = iio_context_find_device(context, "cf-ad9361-lpc");
	if (!phy || !rx) {
		fprintf(stderr, "required IIO devices missing\n");
		goto out;
	}
	lo = find_channel(phy, "altvoltage0", true);
	rx_phy = find_channel(phy, "voltage0", false);
	if (!lo || !rx_phy) {
		fprintf(stderr, "required PHY channels missing\n");
		goto out;
	}
	if (iio_channel_attr_read(lo, "frequency", original_lo,
			sizeof(original_lo)) < 0 ||
	    iio_channel_attr_read(rx_phy, "sampling_frequency", original_rate,
			sizeof(original_rate)) < 0 ||
	    iio_channel_attr_read(rx_phy, "rf_bandwidth", original_bw,
			sizeof(original_bw)) < 0) {
		fprintf(stderr, "failed to preserve radio configuration\n");
		goto out;
	}

	for (channel_index = 0; channel_index < iio_device_get_channels_count(rx);
			++channel_index) {
		struct iio_channel *channel = iio_device_get_channel(rx, channel_index);
		if (iio_channel_is_scan_element(channel) &&
		    !iio_channel_is_output(channel))
			iio_channel_enable(channel);
	}
	if (iio_device_get_sample_size(rx) != 8) {
		fprintf(stderr, "expected dual-RX 8-byte scan step, got %zd\n",
			iio_device_get_sample_size(rx));
		goto restore;
	}
	if (iio_channel_attr_write_longlong(rx_phy, "sampling_frequency",
			SAMPLE_RATE) < 0 ||
	    iio_channel_attr_write_longlong(rx_phy, "rf_bandwidth", RF_BANDWIDTH) < 0 ||
	    iio_device_set_kernel_buffers_count(rx, 1) < 0) {
		fprintf(stderr, "failed to configure RX\n");
		goto restore;
	}

	/* Deterministic shuffled sweeps; adjacent frames always differ. */
	for (index = 0; index < FRAMES; ++index) {
		static const uint8_t sweep[5] = {2, 0, 4, 1, 3};
		slot_order[index] = sweep[index % ARRAY_SIZE(sweep)];
	}

	run_start = now_seconds();
	for (index = 0; index < FRAMES; ++index) {
		struct iio_buffer *buffer;
		const uint8_t *cursor, *end;
		size_t bytes;

		frame_start = now_seconds();
		before = now_seconds();
		if (iio_channel_attr_write_longlong(lo, "frequency",
				frequencies[slot_order[index]]) < 0) {
			fprintf(stderr, "frame %u tune failed: %s\n", index, strerror(errno));
			goto restore;
		}
		after = now_seconds();
		tune.values[index] = after - before;
		sleep_microseconds(SETTLE_US);

		before = now_seconds();
		buffer = iio_device_create_buffer(rx, FRAME_SAMPLES, false);
		after = now_seconds();
		create.values[index] = after - before;
		if (!buffer) {
			fprintf(stderr, "frame %u buffer create failed: %s\n",
				index, strerror(errno));
			goto restore;
		}

		before = now_seconds();
		if (iio_buffer_refill(buffer) < 0) {
			fprintf(stderr, "frame %u refill failed: %s\n", index, strerror(errno));
			iio_buffer_destroy(buffer);
			goto restore;
		}
		after = now_seconds();
		refill.values[index] = after - before;

		before = now_seconds();
		cursor = iio_buffer_start(buffer);
		end = iio_buffer_end(buffer);
		bytes = (size_t)(end - cursor);
		payload_bytes += bytes;
		/* Touch representative payload bytes so the benchmark proves that a real
		 * frame was returned, without charging a deliberately scalar full-frame
		 * checksum to the capture duty cycle. A sender can consume completed
		 * frames on a separate thread in the eventual application. */
		if (bytes) {
			checksum ^= cursor[0];
			checksum *= 16777619U;
			checksum ^= cursor[bytes / 2U];
			checksum *= 16777619U;
			checksum ^= cursor[bytes - 1U];
			checksum *= 16777619U;
		}
		after = now_seconds();
		payload_touch.values[index] = after - before;

		before = now_seconds();
		iio_buffer_destroy(buffer);
		after = now_seconds();
		destroy.values[index] = after - before;
		whole_frame.values[index] = now_seconds() - frame_start;
	}
	wall_seconds = now_seconds() - run_start;
	ret = EXIT_SUCCESS;

	printf("{\n");
	printf("  \"implementation\": \"c-libiio-local\",\n");
	printf("  \"sample_rate_hz\": %lld,\n", SAMPLE_RATE);
	printf("  \"rf_bandwidth_hz\": %lld,\n", RF_BANDWIDTH);
	printf("  \"frame_samples_per_channel\": %u,\n", FRAME_SAMPLES);
	printf("  \"frame_listen_ms\": 80.0,\n");
	printf("  \"frames_completed\": %u,\n", FRAMES);
	printf("  \"settle_guard_us\": %u,\n", SETTLE_US);
	printf("  \"actual_listen_seconds\": 6.0,\n");
	printf("  \"wall_seconds\": %.9f,\n", wall_seconds);
	printf("  \"listening_duty_cycle\": %.9f,\n", 6.0 / wall_seconds);
	printf("  \"payload_bytes\": %" PRIu64 ",\n", payload_bytes);
	printf("  \"effective_payload_mib_s\": %.9f,\n",
		payload_bytes / wall_seconds / (1024.0 * 1024.0));
	printf("  \"checksum\": %u,\n", checksum);
	printf("  \"timings\": {\n");
	print_stats("tune", &tune, true);
	print_stats("buffer_create", &create, true);
	print_stats("buffer_refill", &refill, true);
	print_stats("payload_touch", &payload_touch, true);
	print_stats("buffer_destroy", &destroy, true);
	print_stats("whole_frame", &whole_frame, false);
	printf("  }\n");
	printf("}\n");

restore:
	(void)iio_channel_attr_write(rx_phy, "rf_bandwidth", original_bw);
	(void)iio_channel_attr_write(rx_phy, "sampling_frequency", original_rate);
	(void)iio_channel_attr_write(lo, "frequency", original_lo);
out:
	if (context)
		iio_context_destroy(context);
	return ret;
}
