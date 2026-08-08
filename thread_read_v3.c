#define _GNU_SOURCE

#include "thread_read_v3.h"

#include "epoll_loop.h"
#include "spf_ip_protocol.h"
#include "utils.h"

#include <spf/spf_gain_read.h>
#include <spf/spf_gain_sampler.h>
#include <spf/spf_radio_frame_v3.h>
#include <spf/spf_rssi_read.h>

#include <errno.h>
#include <pthread.h>
#include <poll.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/epoll.h>
#include <sys/eventfd.h>
#include <sys/socket.h>
#include <sys/uio.h>
#include <unistd.h>

#define SPF_SENDMMSG_BATCH 1024U
#define DEBUG_PRINT(...) if (debug) printf("ReadV3: "__VA_ARGS__)

typedef struct
{
	THREAD_READ_V3_Args_t *args;
	bool keep_running;
	int epoll_fd;
	struct iio_context *iio_ctx;
	struct iio_device *iio_rx;
	struct iio_device *phy;
	struct iio_buffer *iio_buffer;
	uint32_t timestamp_control_previous;
	bool timestamp_control_configured;
	spf_gain_table_t gain_table;
	spf_gain_sampler_t sampler;
	bool sampler_started;
	spf_rssi_pair_t previous_rssi;
	size_t iio_bytes;
	size_t iq_bytes;
	size_t header_bytes;
	size_t frame_bytes;
	uint8_t *frame;
	spf_gain_observation_v3_t observations[SPF_MAX_GAIN_OBSERVATIONS];
	spf_ip_fragment_v1_t *fragment_headers;
	struct mmsghdr *messages;
	struct iovec *iovs;
	size_t fragment_count;
	uint64_t buffer_sequence;
} state_v3_t;

extern bool debug;

static int handle_quit(state_v3_t *state);
static int handle_iio(state_v3_t *state);
static bool initialize(state_v3_t *state);
static void cleanup(state_v3_t *state);
static bool send_frame(state_v3_t *state);
static void report_startup(const state_v3_t *state, uint64_t result);
static bool wait_for_run(const state_v3_t *state);

void *THREAD_READ_V3_Entrypoint(void *opaque)
{
	state_v3_t state;
	memset(&state, 0, sizeof(state));
	state.args = (THREAD_READ_V3_Args_t *)opaque;
	state.epoll_fd = -1;
	pthread_setname_np(pthread_self(), "IP_SDR_V3_RX");
	UTILS_SetThreadRealtimePriority();
	UTILS_SetThreadAffinity(1);
	if (!initialize(&state))
	{
		report_startup(&state, 2);
		cleanup(&state);
		return NULL;
	}
	report_startup(&state, 1);
	if (!wait_for_run(&state))
	{
		cleanup(&state);
		return NULL;
	}
	state.keep_running = true;
	while (state.keep_running)
	{
		if (EPOLL_LOOP_Run(state.epoll_fd, 30000, &state) < 0)
			break;
	}
	cleanup(&state);
	return NULL;
}

static bool initialize(state_v3_t *state)
{
	THREAD_READ_V3_Args_t *args = state->args;
	if (args == NULL || args->quit_event_fd < 0 || args->output_fd < 0 ||
		args->startup_event_fd < 0 || args->run_event_fd < 0 ||
		args->stream_id == 0 || args->frame_count == 0 ||
		args->samples_per_channel == 0 || args->iio_channels != 0x0f ||
		args->gain_observation_capacity == 0)
		return false;
	state->header_bytes = spf_radio_frame_v3_header_bytes(
		args->gain_observation_capacity, args->gain_event_capacity);
	if (state->header_bytes == 0)
		return false;

	state->epoll_fd = epoll_create1(0);
	if (state->epoll_fd < 0)
		return false;
	struct epoll_event event = {.events = EPOLLIN, .data.ptr = handle_quit};
	if (epoll_ctl(state->epoll_fd,
		EPOLL_CTL_ADD,
		args->quit_event_fd,
		&event) < 0)
		return false;

	state->iio_ctx = iio_create_local_context();
	if (state->iio_ctx == NULL)
		return false;
	state->iio_rx = iio_context_find_device(state->iio_ctx, "cf-ad9361-lpc");
	state->phy = iio_context_find_device(state->iio_ctx, "ad9361-phy");
	if (state->iio_rx == NULL || state->phy == NULL)
		return false;
	for (unsigned int index = 0;
		index < iio_device_get_channels_count(state->iio_rx);
		++index)
		iio_channel_disable(iio_device_get_channel(state->iio_rx, index));
	for (unsigned int index = 0; index < 32; ++index)
	{
		if ((args->iio_channels & (UINT32_C(1) << index)) == 0)
			continue;
		struct iio_channel *channel = iio_device_get_channel(state->iio_rx, index);
		if (channel == NULL)
			return false;
		iio_channel_enable(channel);
	}
	if (iio_device_reg_read(state->iio_rx,
		SPF_ADC_TIMESTAMP_CONTROL_REG,
		&state->timestamp_control_previous) != 0)
		return false;
	const uint32_t timestamp_control =
		((uint32_t)args->samples_per_channel << 1) |
		(state->timestamp_control_previous & UINT32_C(1));
	if (iio_device_reg_write(state->iio_rx,
		SPF_ADC_TIMESTAMP_CONTROL_REG,
		timestamp_control) != 0)
		return false;
	state->timestamp_control_configured = true;
	state->iio_buffer = iio_device_create_buffer(
		state->iio_rx, args->samples_per_channel + 1, false);
	if (state->iio_buffer == NULL || iio_buffer_step(state->iio_buffer) != 8)
		return false;
	state->iio_bytes = (args->samples_per_channel + 1) * 8;
	state->iq_bytes = args->samples_per_channel * 8;
	state->frame_bytes = state->header_bytes + state->iq_bytes;
	state->frame = malloc(state->frame_bytes);
	if (state->frame == NULL)
		return false;

	if (!spf_gain_is_full_table_mode(state->phy) ||
		!spf_gain_is_digital_gain_disabled(state->phy) ||
		!spf_gain_table_load(state->phy, &state->gain_table))
		return false;
	state->previous_rssi = spf_rssi_read_pair(state->phy);
	if (!spf_gain_sampler_start(
		&state->sampler, args->gain_observation_interval_samples))
		return false;
	state->sampler_started = true;

	state->fragment_count = spf_ip_fragment_count(
		state->frame_bytes, args->udp_datagram_bytes);
	if (state->fragment_count == 0)
		return false;
	state->fragment_headers = calloc(
		state->fragment_count, sizeof(*state->fragment_headers));
	state->messages = calloc(state->fragment_count, sizeof(*state->messages));
	state->iovs = calloc(state->fragment_count * 2, sizeof(*state->iovs));
	if (state->fragment_headers == NULL || state->messages == NULL ||
		state->iovs == NULL)
		return false;
	for (size_t index = 0; index < state->fragment_count; ++index)
	{
		state->messages[index].msg_hdr.msg_name = &args->addr;
		state->messages[index].msg_hdr.msg_namelen = sizeof(args->addr);
		state->messages[index].msg_hdr.msg_iov = &state->iovs[index * 2];
		state->messages[index].msg_hdr.msg_iovlen = 2;
		state->iovs[index * 2].iov_base = &state->fragment_headers[index];
		state->iovs[index * 2].iov_len = sizeof(state->fragment_headers[index]);
	}
	event.events = EPOLLIN;
	event.data.ptr = handle_iio;
	if (epoll_ctl(state->epoll_fd,
		EPOLL_CTL_ADD,
		iio_buffer_get_poll_fd(state->iio_buffer),
		&event) < 0)
		return false;
	DEBUG_PRINT("ready: samples=%zu frame=%zu fragments=%zu stream=%llu\n",
		args->samples_per_channel,
		state->frame_bytes,
		state->fragment_count,
		(unsigned long long)args->stream_id);
	return true;
}

static void report_startup(const state_v3_t *state, uint64_t result)
{
	if (state->args != NULL && state->args->startup_event_fd >= 0)
		(void)write(state->args->startup_event_fd, &result, sizeof(result));
}

static bool wait_for_run(const state_v3_t *state)
{
	struct pollfd events[2] = {
		{.fd = state->args->run_event_fd, .events = POLLIN},
		{.fd = state->args->quit_event_fd, .events = POLLIN},
	};
	for (;;)
	{
		const int ready = poll(events, 2, -1);
		if (ready < 0 && errno == EINTR)
			continue;
		if (ready < 0 || (events[1].revents & POLLIN) != 0)
			return false;
		if ((events[0].revents & POLLIN) != 0)
		{
			uint64_t value = 0;
			return read(state->args->run_event_fd,
				&value,
				sizeof(value)) == (ssize_t)sizeof(value);
		}
	}
}

static int handle_quit(state_v3_t *state)
{
	/* Main owns and resets this eventfd after joining the worker. */
	state->keep_running = false;
	return 0;
}

static int handle_iio(state_v3_t *state)
{
	const ssize_t received = iio_buffer_refill(state->iio_buffer);
	if (received != (ssize_t)state->iio_bytes)
		return -1;
	const uint8_t *iio = iio_buffer_start(state->iio_buffer);
	uint64_t first_sample_sequence;
	memcpy(&first_sample_sequence, iio, sizeof(first_sample_sequence));
	iio += sizeof(first_sample_sequence);
	const spf_rssi_pair_t current_rssi = spf_rssi_read_pair(state->phy);
	uint32_t observation_overflow = 0;
	const uint16_t observation_count = spf_gain_sampler_collect(
		&state->sampler,
		first_sample_sequence,
		(uint32_t)state->args->samples_per_channel,
		state->observations,
		state->args->gain_observation_capacity,
		&observation_overflow);
	const spf_radio_frame_v3_args_t frame_args = {
		.metadata_features = state->args->metadata_features,
		.stream_id = state->args->stream_id,
		.buffer_sequence = state->buffer_sequence,
		.first_sample_sequence = first_sample_sequence,
		.samples_per_channel = (uint32_t)state->args->samples_per_channel,
		.iq_payload_bytes = (uint32_t)state->iq_bytes,
		.enabled_scan_mask = state->args->iio_channels,
		.gain_observation_interval_samples =
			state->args->gain_observation_interval_samples,
		.gain_observations = state->observations,
		.gain_observation_count = observation_count,
		.gain_observation_capacity = state->args->gain_observation_capacity,
		.gain_observation_overflow_count = observation_overflow,
		.gain_event_capacity = state->args->gain_event_capacity,
		.rssi_start = {
			.rx1_qdb = state->previous_rssi.rx1_qdb,
			.rx2_qdb = state->previous_rssi.rx2_qdb,
			.valid = state->previous_rssi.valid,
			.duration_ns = state->previous_rssi.duration_ns,
		},
		.rssi_end = {
			.rx1_qdb = current_rssi.rx1_qdb,
			.rx2_qdb = current_rssi.rx2_qdb,
			.valid = current_rssi.valid,
			.duration_ns = current_rssi.duration_ns,
		},
	};
	if (!spf_radio_frame_v3_build(
		state->frame, state->header_bytes, &frame_args))
		return -1;
	memcpy(state->frame + state->header_bytes, iio, state->iq_bytes);
	if (!send_frame(state))
		return -1;
	state->previous_rssi = current_rssi;
	state->buffer_sequence++;
	if (state->buffer_sequence >= state->args->frame_count)
		state->keep_running = false;
	return 0;
}

static bool send_frame(state_v3_t *state)
{
	if (!spf_ip_fragment_plan(state->fragment_headers,
		state->fragment_count,
		state->frame,
		state->frame_bytes,
		state->args->stream_id,
		state->buffer_sequence,
		state->args->udp_datagram_bytes))
		return false;
	for (size_t index = 0; index < state->fragment_count; ++index)
	{
		state->iovs[index * 2 + 1].iov_base =
			state->frame + state->fragment_headers[index].fragment_offset;
		state->iovs[index * 2 + 1].iov_len =
			state->fragment_headers[index].fragment_bytes;
		state->messages[index].msg_len = 0;
	}
	for (size_t offset = 0; offset < state->fragment_count;)
	{
		const size_t remaining = state->fragment_count - offset;
		const unsigned int batch = (unsigned int)(remaining < SPF_SENDMMSG_BATCH
			? remaining : SPF_SENDMMSG_BATCH);
		const int sent = sendmmsg(
			state->args->output_fd, &state->messages[offset], batch, 0);
		if (sent > 0)
		{
			offset += (size_t)sent;
			continue;
		}
		if (sent < 0 && errno == EINTR)
			continue;
		if (sent < 0 && (errno == EAGAIN || errno == EWOULDBLOCK))
		{
			struct pollfd writable = {
				.fd = state->args->output_fd,
				.events = POLLOUT,
			};
			if (poll(&writable, 1, 1000) > 0)
				continue;
		}
		return false;
	}
	return true;
}

static void cleanup(state_v3_t *state)
{
	if (state->sampler_started)
		spf_gain_sampler_stop(&state->sampler);
	if (state->timestamp_control_configured && state->iio_rx != NULL)
		iio_device_reg_write(state->iio_rx,
			SPF_ADC_TIMESTAMP_CONTROL_REG,
			state->timestamp_control_previous);
	if (state->iio_buffer != NULL)
		iio_buffer_destroy(state->iio_buffer);
	if (state->iio_ctx != NULL)
		iio_context_destroy(state->iio_ctx);
	if (state->epoll_fd >= 0)
		close(state->epoll_fd);
	free(state->fragment_headers);
	free(state->messages);
	free(state->iovs);
	free(state->frame);
}
