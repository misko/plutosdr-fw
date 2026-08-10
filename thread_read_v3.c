#define _GNU_SOURCE

#include "thread_read_v3.h"

#include "epoll_loop.h"
#include "spf_ip_frame_queue.h"
#include "spf_ip_protocol.h"
#include "spf_ip_tx_policy.h"
#include "utils.h"

#include <spf/spf_gain_read.h>
#include <spf/spf_gain_sampler.h>
#include <spf/spf_radio_frame_v3.h>
#include <spf/spf_rssi_read.h>

#include <errno.h>
#include <netinet/udp.h>
#include <pthread.h>
#include <poll.h>
#include <sched.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/epoll.h>
#include <sys/eventfd.h>
#include <sys/socket.h>
#include <sys/uio.h>
#include <time.h>
#include <unistd.h>

/*
 * UDP GSO reached Linux before every supported Buildroot userspace header
 * exposed its socket-option number. The Pluto runtime kernel supports the
 * option, but its pinned headers need the stable UAPI value supplied here.
 */
#ifndef UDP_SEGMENT
#define UDP_SEGMENT 103
#endif

#define DEBUG_PRINT(...) if (debug) printf("ReadV3: "__VA_ARGS__)

/* Match the bounded DMA headroom proven by the direct-USB RX path. */
#define SPF_IP_IIO_KERNEL_BUFFER_COUNT 8U

typedef struct
{
	uint8_t *frame;
	uint64_t sequence;
} frame_slot_v3_t;

typedef struct
{
	THREAD_READ_V3_Args_t *args;
	bool keep_running;
	int epoll_fd;
	int sender_event_fd;
	int iio_poll_fd;
	bool iio_poll_registered;
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
	frame_slot_v3_t *frame_slots;
	size_t frame_slot_count;
	size_t frames_captured;
	size_t frames_sent;
	spf_ip_frame_queue_t ready_queue;
	size_t *ready_queue_storage;
	pthread_mutex_t queue_mutex;
	pthread_cond_t queue_condition;
	bool queue_mutex_initialized;
	bool queue_condition_initialized;
	pthread_t sender_thread;
	bool sender_started;
	bool sender_stop;
	bool capture_complete;
	bool sender_failed;
	spf_gain_observation_v3_t observations[SPF_MAX_GAIN_OBSERVATIONS];
	spf_ip_fragment_v1_t *fragment_headers;
	struct mmsghdr *messages;
	struct iovec *iovs;
	uint32_t gso_segments_per_send;
	size_t fragment_count;
	uint32_t send_batch;
	uint32_t pacing_interval_us;
	uint64_t buffer_sequence;
	uint32_t startup_frames_discarded;
} state_v3_t;

extern bool debug;

static int handle_quit(state_v3_t *state);
static int handle_iio(state_v3_t *state);
static int handle_sender_event(state_v3_t *state);
static bool initialize(state_v3_t *state);
static void cleanup(state_v3_t *state);
static bool send_frame(state_v3_t *state,
	const uint8_t *frame,
	uint64_t sequence);
static bool send_frame_gso(state_v3_t *state,
	const uint8_t *frame,
	uint64_t sequence);
static void *sender_entrypoint(void *opaque);
static void signal_sender_result(state_v3_t *state, uint64_t result);
static void report_startup(const state_v3_t *state, uint64_t result);
static bool wait_for_run(const state_v3_t *state);
static bool set_thread_affinity(pthread_t thread, int cpu_id);
static bool sleep_until_ns(uint64_t deadline_ns);

static uint64_t monotonic_ns(void)
{
	struct timespec now;
	if (clock_gettime(CLOCK_MONOTONIC, &now) != 0)
		return 0;
	return (uint64_t)now.tv_sec * UINT64_C(1000000000) +
		(uint64_t)now.tv_nsec;
}

void *THREAD_READ_V3_Entrypoint(void *opaque)
{
	state_v3_t state;
	memset(&state, 0, sizeof(state));
	state.args = (THREAD_READ_V3_Args_t *)opaque;
	state.epoll_fd = -1;
	state.sender_event_fd = -1;
	state.iio_poll_fd = -1;
	pthread_setname_np(pthread_self(), "IP_SDR_V3_RX");
	/* DMA ownership must win over packetization to preserve IQ continuity. */
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
		args->gain_observation_capacity == 0 ||
		args->target_payload_bytes_per_second == 0 ||
		args->pacing_interval_us == 0)
		return false;
	if (pthread_mutex_init(&state->queue_mutex, NULL) != 0)
		return false;
	state->queue_mutex_initialized = true;
	if (pthread_cond_init(&state->queue_condition, NULL) != 0)
		return false;
	state->queue_condition_initialized = true;
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
	state->sender_event_fd = eventfd(0, EFD_NONBLOCK);
	if (state->sender_event_fd < 0)
		return false;
	event.events = EPOLLIN;
	event.data.ptr = handle_sender_event;
	if (epoll_ctl(state->epoll_fd,
		EPOLL_CTL_ADD,
		state->sender_event_fd,
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
	const int kernel_buffer_result = iio_device_set_kernel_buffers_count(
		state->iio_rx, SPF_IP_IIO_KERNEL_BUFFER_COUNT);
	if (kernel_buffer_result != 0)
	{
		fprintf(stderr,
			"Failed to configure %u IIO kernel buffers: %d\n",
			SPF_IP_IIO_KERNEL_BUFFER_COUNT,
			kernel_buffer_result);
		return false;
	}
	state->iio_buffer = iio_device_create_buffer(
		state->iio_rx, args->samples_per_channel + 1, false);
	if (state->iio_buffer == NULL || iio_buffer_step(state->iio_buffer) != 8)
		return false;
	state->iio_bytes = (args->samples_per_channel + 1) * 8;
	state->iq_bytes = args->samples_per_channel * 8;
	state->frame_bytes = state->header_bytes + state->iq_bytes;
	state->frame_slot_count = args->frame_count;
	state->frame_slots = calloc(
		state->frame_slot_count, sizeof(*state->frame_slots));
	state->ready_queue_storage = calloc(
		state->frame_slot_count, sizeof(*state->ready_queue_storage));
	if (state->frame_slots == NULL || state->ready_queue_storage == NULL ||
		!spf_ip_frame_queue_init(&state->ready_queue,
			state->ready_queue_storage,
			state->frame_slot_count))
		return false;
	for (size_t index = 0; index < state->frame_slot_count; ++index)
	{
		state->frame_slots[index].frame = malloc(state->frame_bytes);
		if (state->frame_slots[index].frame == NULL)
			return false;
	}

	if (!spf_gain_is_full_table_mode(state->phy) ||
		!spf_gain_is_digital_gain_disabled(state->phy) ||
		!spf_gain_table_load(state->phy, &state->gain_table))
		return false;
	state->previous_rssi = spf_rssi_read_pair(state->phy);
	if (!spf_gain_sampler_start(
		&state->sampler, args->gain_observation_interval_samples))
		return false;
	state->sampler_started = true;
	/*
	 * The RX worker is continuously runnable at 30 MS/s.  Move the normal-
	 * priority sampler off its real-time CPU before DMA starts; otherwise it
	 * is starved and frames fail closed with no gain observations.
	 */
	if (!set_thread_affinity(state->sampler.thread, 0))
		return false;

	/*
	 * iio_device_create_buffer() starts DMA before the sampler has loaded the
	 * gain table.  Discard that one startup-prefetched block after the sampler
	 * is ready; otherwise its inline timestamp can predate every available gain
	 * observation and the first protocol-v3 frame must fail closed.
	 */
	const ssize_t discarded = iio_buffer_refill(state->iio_buffer);
	if (discarded != (ssize_t)state->iio_bytes)
		return false;

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
	/*
	 * UDP GSO lets the 5.15 network stack route one batch before segmenting it
	 * into MTU-safe datagrams.  This removes the Zynq packet-per-second ceiling
	 * without IP fragmentation or a wire-format change.
	 */
	if (args->udp_datagram_bytes <= UINT16_C(1472))
	{
		state->gso_segments_per_send = spf_ip_gso_segments_per_send(
			args->udp_datagram_bytes);
		if (state->gso_segments_per_send == 0)
			return false;
	}
	for (size_t index = 0; index < state->fragment_count; ++index)
	{
		state->messages[index].msg_hdr.msg_name = &args->addr;
		state->messages[index].msg_hdr.msg_namelen = sizeof(args->addr);
		state->messages[index].msg_hdr.msg_iov = &state->iovs[index * 2];
		state->messages[index].msg_hdr.msg_iovlen = 2;
		state->iovs[index * 2].iov_base = &state->fragment_headers[index];
		state->iovs[index * 2].iov_len = sizeof(state->fragment_headers[index]);
	}
	const size_t payload_bytes_per_datagram =
		args->udp_datagram_bytes - sizeof(spf_ip_fragment_v1_t);
	state->pacing_interval_us = args->pacing_interval_us;
	state->send_batch = spf_ip_tx_batch_size(
		payload_bytes_per_datagram,
		args->target_payload_bytes_per_second,
		state->pacing_interval_us);
	if (state->send_batch == 0)
		return false;
	event.events = EPOLLIN;
	event.data.ptr = handle_iio;
	state->iio_poll_fd = iio_buffer_get_poll_fd(state->iio_buffer);
	if (epoll_ctl(state->epoll_fd,
		EPOLL_CTL_ADD,
		state->iio_poll_fd,
		&event) < 0)
		return false;
	state->iio_poll_registered = true;
	if (pthread_create(
		&state->sender_thread, NULL, sender_entrypoint, state) != 0)
		return false;
	state->sender_started = true;
	DEBUG_PRINT("ready: samples=%zu frame=%zu slots=%zu fragments=%zu batch=%u/%uus stream=%llu\n",
		args->samples_per_channel,
		state->frame_bytes,
		state->frame_slot_count,
		state->fragment_count,
		state->send_batch,
		state->pacing_interval_us,
		(unsigned long long)args->stream_id);
	return true;
}

static void report_startup(const state_v3_t *state, uint64_t result)
{
	if (state->args != NULL && state->args->startup_event_fd >= 0)
	{
		const ssize_t written = write(
			state->args->startup_event_fd, &result, sizeof(result));
		if (written != (ssize_t)sizeof(result))
			perror("Failed to report RX startup result");
	}
}

static bool set_thread_affinity(pthread_t thread, int cpu_id)
{
	cpu_set_t affinity;
	CPU_ZERO(&affinity);
	CPU_SET(cpu_id, &affinity);
	const int rc = pthread_setaffinity_np(thread, sizeof(affinity), &affinity);
	if (rc != 0)
	{
		errno = rc;
		perror("Failed to set helper thread affinity");
		return false;
	}
	return true;
}

static bool sleep_until_ns(uint64_t deadline_ns)
{
	const struct timespec deadline = {
		.tv_sec = (time_t)(deadline_ns / UINT64_C(1000000000)),
		.tv_nsec = (long)(deadline_ns % UINT64_C(1000000000)),
	};
	int rc;
	do
	{
		rc = clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &deadline, NULL);
	} while (rc == EINTR);
	if (rc != 0)
	{
		errno = rc;
		perror("Failed to pace direct-IP sender");
		return false;
	}
	return true;
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

static int handle_sender_event(state_v3_t *state)
{
	uint64_t result = 0;
	if (read(state->sender_event_fd, &result, sizeof(result)) !=
		(ssize_t)sizeof(result))
		return -1;
	state->keep_running = false;
	return result == 1 ? 0 : -1;
}

static int handle_iio(state_v3_t *state)
{
	const uint64_t handler_started_ns = debug ? monotonic_ns() : 0;
	if (state->frames_captured >= state->frame_slot_count)
		return -1;
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
	const spf_gain_frame_decision_t frame_decision = spf_gain_frame_decide(
		state->buffer_sequence,
		observation_count,
		state->startup_frames_discarded);
	if (frame_decision == SPF_GAIN_FRAME_DISCARD_STARTUP)
	{
		/* Never send startup IQ that predates the first gain observation. */
		state->startup_frames_discarded++;
		DEBUG_PRINT(
			"discarded startup frame without a gain observation (%u/%u)\n",
			state->startup_frames_discarded,
			SPF_GAIN_STARTUP_DISCARD_LIMIT);
		return 0;
	}
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
	frame_slot_v3_t *slot = &state->frame_slots[state->frames_captured];
	slot->sequence = state->buffer_sequence;
	if (!spf_radio_frame_v3_build(
		slot->frame, state->header_bytes, &frame_args))
		return -1;
	memcpy(slot->frame + state->header_bytes, iio, state->iq_bytes);
	if (pthread_mutex_lock(&state->queue_mutex) != 0)
		return -1;
	const bool queued = spf_ip_frame_queue_push(
		&state->ready_queue, state->frames_captured);
	if (queued)
	{
		state->frames_captured++;
		state->capture_complete =
			state->frames_captured == state->frame_slot_count;
		pthread_cond_signal(&state->queue_condition);
	}
	pthread_mutex_unlock(&state->queue_mutex);
	if (!queued)
		return -1;
	state->previous_rssi = current_rssi;
	state->buffer_sequence++;
	if (state->capture_complete && state->iio_poll_registered)
	{
		if (epoll_ctl(state->epoll_fd,
			EPOLL_CTL_DEL,
			state->iio_poll_fd,
			NULL) < 0)
			return -1;
		state->iio_poll_registered = false;
	}
	DEBUG_PRINT(
		"captured=%zu sequence=%llu observations=%u rssi_ns=%u handler_ns=%llu\n",
		state->frames_captured,
		(unsigned long long)first_sample_sequence,
		observation_count,
		current_rssi.duration_ns,
		(unsigned long long)(monotonic_ns() - handler_started_ns));
	return 0;
}

static void *sender_entrypoint(void *opaque)
{
	state_v3_t *state = opaque;
	pthread_setname_np(pthread_self(), "IP_SDR_V3_TX");
	/*
	 * The finite queue is intentionally capture-first.  Once DMA is stopped,
	 * reuse CPU 1 for packetization and leave CPU 0 to the gain sampler and
	 * Ethernet IRQ while the buffered frames drain.
	 */
	UTILS_SetThreadNormalPriority();
	UTILS_SetThreadAffinity(1);
	for (;;)
	{
		if (pthread_mutex_lock(&state->queue_mutex) != 0)
			break;
		while (!state->capture_complete && !state->sender_stop)
			pthread_cond_wait(&state->queue_condition, &state->queue_mutex);
		if (state->sender_stop)
		{
			pthread_mutex_unlock(&state->queue_mutex);
			return NULL;
		}
		size_t slot_index = 0;
		const bool have_frame = spf_ip_frame_queue_pop(
			&state->ready_queue, &slot_index);
		const bool impossible_empty = !have_frame && state->capture_complete;
		pthread_mutex_unlock(&state->queue_mutex);
		if (impossible_empty)
			break;
		if (!have_frame)
			continue;
		frame_slot_v3_t *slot = &state->frame_slots[slot_index];
		const uint64_t send_started_ns = debug ? monotonic_ns() : 0;
		if (!send_frame(state, slot->frame, slot->sequence))
			break;
		DEBUG_PRINT(
			"sent=%zu sequence=%llu sender_ns=%llu\n",
			state->frames_sent + 1,
			(unsigned long long)slot->sequence,
			(unsigned long long)(monotonic_ns() - send_started_ns));
		state->frames_sent++;
		if (state->frames_sent == state->frame_slot_count)
		{
			signal_sender_result(state, 1);
			return NULL;
		}
	}
	state->sender_failed = true;
	signal_sender_result(state, 2);
	return NULL;
}

static void signal_sender_result(state_v3_t *state, uint64_t result)
{
	const ssize_t written = write(
		state->sender_event_fd, &result, sizeof(result));
	if (written != (ssize_t)sizeof(result))
		perror("Failed to report sender result");
}

static bool send_frame(state_v3_t *state,
	const uint8_t *frame,
	uint64_t sequence)
{
	if (!spf_ip_fragment_plan(state->fragment_headers,
		state->fragment_count,
		frame,
		state->frame_bytes,
		state->args->stream_id,
		sequence,
		state->args->udp_datagram_bytes))
		return false;
	for (size_t index = 0; index < state->fragment_count; ++index)
	{
		state->iovs[index * 2 + 1].iov_base =
			(void *)(frame + state->fragment_headers[index].fragment_offset);
		state->iovs[index * 2 + 1].iov_len =
			state->fragment_headers[index].fragment_bytes;
		state->messages[index].msg_len = 0;
	}
	if (state->gso_segments_per_send != 0)
		return send_frame_gso(state, frame, sequence);
	const uint64_t pacing_started_ns = monotonic_ns();
	uint64_t payload_bytes_sent = 0;
	for (size_t offset = 0; offset < state->fragment_count;)
	{
		const size_t remaining = state->fragment_count - offset;
		const unsigned int batch = (unsigned int)(remaining < state->send_batch
			? remaining : state->send_batch);
		const int sent = sendmmsg(
			state->args->output_fd, &state->messages[offset], batch, 0);
		if (sent > 0)
		{
			for (int index = 0; index < sent; ++index)
				payload_bytes_sent += state->fragment_headers[
					offset + (size_t)index].fragment_bytes;
			offset += (size_t)sent;
			if (offset < state->fragment_count)
			{
				const uint64_t deadline_ns = spf_ip_tx_deadline_ns(
					pacing_started_ns,
					payload_bytes_sent,
					state->args->target_payload_bytes_per_second);
				if (deadline_ns == 0 || !sleep_until_ns(deadline_ns))
					return false;
			}
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

static bool send_frame_gso(state_v3_t *state,
	const uint8_t *frame,
	uint64_t sequence)
{
	(void)frame;
	(void)sequence;
	const uint64_t pacing_started_ns = monotonic_ns();
	uint64_t payload_bytes_sent = 0;
	for (size_t offset = 0; offset < state->fragment_count;)
	{
		const size_t remaining = state->fragment_count - offset;
		const size_t segment_count = remaining < state->gso_segments_per_send
			? remaining
			: state->gso_segments_per_send;
		size_t gso_bytes = 0;
		uint64_t group_payload_bytes = 0;
		for (size_t index = 0; index < segment_count; ++index)
		{
			const spf_ip_fragment_v1_t *header =
				&state->fragment_headers[offset + index];
			gso_bytes += sizeof(*header) + header->fragment_bytes;
			group_payload_bytes += header->fragment_bytes;
		}

		union
		{
			struct cmsghdr alignment;
			uint8_t bytes[CMSG_SPACE(sizeof(uint16_t))];
		} control;
		memset(&control, 0, sizeof(control));
		struct msghdr message = {
			.msg_name = &state->args->addr,
			.msg_namelen = sizeof(state->args->addr),
			.msg_iov = &state->iovs[offset * 2],
			.msg_iovlen = segment_count * 2,
			.msg_control = control.bytes,
			.msg_controllen = sizeof(control.bytes),
		};
		struct cmsghdr *cmsg = CMSG_FIRSTHDR(&message);
		if (cmsg == NULL)
			return false;
		cmsg->cmsg_level = SOL_UDP;
		cmsg->cmsg_type = UDP_SEGMENT;
		cmsg->cmsg_len = CMSG_LEN(sizeof(uint16_t));
		const uint16_t segment_bytes =
			(uint16_t)state->args->udp_datagram_bytes;
		memcpy(CMSG_DATA(cmsg), &segment_bytes, sizeof(segment_bytes));

		ssize_t sent;
		do
		{
			sent = sendmsg(state->args->output_fd, &message, 0);
		} while (sent < 0 && errno == EINTR);
		if (sent < 0 && (errno == EAGAIN || errno == EWOULDBLOCK))
		{
			struct pollfd writable = {
				.fd = state->args->output_fd,
				.events = POLLOUT,
			};
			if (poll(&writable, 1, 1000) > 0)
				continue;
		}
		if (sent != (ssize_t)gso_bytes)
		{
			if (sent < 0)
				perror("UDP GSO send failed");
			return false;
		}
		offset += segment_count;
		payload_bytes_sent += group_payload_bytes;
		if (offset < state->fragment_count)
		{
			const uint64_t deadline_ns = spf_ip_tx_deadline_ns(
				pacing_started_ns,
				payload_bytes_sent,
				state->args->target_payload_bytes_per_second);
			if (deadline_ns == 0 || !sleep_until_ns(deadline_ns))
				return false;
		}
	}
	return true;
}

static void cleanup(state_v3_t *state)
{
	if (state->sender_started)
	{
		if (state->queue_mutex_initialized)
		{
			pthread_mutex_lock(&state->queue_mutex);
			state->sender_stop = true;
			pthread_cond_broadcast(&state->queue_condition);
			pthread_mutex_unlock(&state->queue_mutex);
		}
		pthread_join(state->sender_thread, NULL);
		state->sender_started = false;
	}
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
	if (state->sender_event_fd >= 0)
		close(state->sender_event_fd);
	free(state->fragment_headers);
	free(state->messages);
	free(state->iovs);
	if (state->frame_slots != NULL)
	{
		for (size_t index = 0; index < state->frame_slot_count; ++index)
			free(state->frame_slots[index].frame);
	}
	free(state->frame_slots);
	free(state->ready_queue_storage);
	if (state->queue_condition_initialized)
		pthread_cond_destroy(&state->queue_condition);
	if (state->queue_mutex_initialized)
		pthread_mutex_destroy(&state->queue_mutex);
}
