/* Use non portable functions */
#define _GNU_SOURCE

/* Public header */
#include "thread_read.h"

/* Standard / system libraries */
#include <errno.h>
#include <inttypes.h>
#include <pthread.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/epoll.h>
#include <sys/eventfd.h>
#include <sys/timerfd.h>
#include <time.h>
#include <unistd.h>

/* libIIO */
#include <iio.h>

/* AsyncIO library */
#include "libaio.h"

/* Local modules */
#include "usb_buff.h"
#include "ring_buffer.h"
#include "epoll_loop.h"
#include "utils.h"
#include "spf_gain_metadata.h"
#include "spf_gain_read.h"
#include "spf_rssi_read.h"
#include "spf_buffer_policy.h"
#include "spf_cleanup_plan.h"

/* Set the following to periodically report statistics */
#ifndef GENERATE_STATS
#define GENERATE_STATS (0)
#endif

/* Set stats period */
#ifndef STATS_PERIOD_SECS
#define STATS_PERIOD_SECS (5)
#endif

/* Macros */
#define ARRAY_SIZE(x) (sizeof(x) / sizeof((x)[0]))
#define DEBUG_PRINT(...) if (debug) printf("Read: "__VA_ARGS__)

/* Type definitions */
typedef struct
{
	/* Thread args */
	THREAD_READ_Args_t *thread_args;
	uint32_t acquired_resources;
	uint32_t buffers_allocated;
	struct iio_context *iio_ctx;

	/* Keep running */
	bool keep_running;
	bool worker_ready;

	/* IIO sample buffer */
	struct iio_buffer *iio_rx_buffer;

	/* Local AD936x PHY used for endpoint gain snapshots. */
	struct iio_device *iio_dev_phy;
	bool full_gain_table_mode;
	bool digital_gain_disabled;
	spf_gain_table_t gain_table;
	spf_gain_pair_t previous_gain;
	spf_rssi_pair_t previous_rssi;
	uint64_t gain_read_failures;
	uint64_t rssi_read_failures;

	/* Size of USB buffer (bytes) */
	size_t usb_buffer_size;

	/* Size of the IQ portion of a versioned transfer. */
	size_t iq_payload_size;

	/* Epoll and IIO poll state, used to stop finite capture cleanly. */
	int epoll_fd;
	int iio_poll_fd;
	bool iio_poll_registered;

	/* Versioned finite-stream state. */
	bool metadata_enabled;
	bool metadata_v2;
	size_t metadata_header_size;
	uint32_t frames_remaining;
	uint64_t buffer_sequence;
	uint32_t frames_completed_in_stream;
	bool overflow_seen;

	/* AIO context */
	io_context_t io_ctx;

	/* AIO completion eventfd */
	int aio_eventfd;

	/* List of buffers */
	usb_buf_t* buffers[SPF_USB_BUFFER_LIMIT];
	uint32_t buffer_count;

	/* Ring buffer of unused AIO requests */
	RING_BUFFER_Ctx_t ring_buf_ctx;
	usb_buf_t* ring_buf_data[SPF_USB_BUFFER_LIMIT];

	#if GENERATE_STATS
	/* Stats reporting timer */
	int stats_timerfd;

	/* Overflow count */
	uint32_t overflows;

	/* Read period timer */
	UTILS_TimeStats_t read_period;

	/* Read duration timer */
	UTILS_TimeStats_t read_dur;
	#endif

} state_t;

/* Epoll event handler */
typedef int (*epoll_event_handler)(state_t *state);

/* Global variables */
extern bool debug;

/* Private functions */
static int handle_eventfd_thread(state_t *state);
static int handle_eventfd_aio(state_t *state);
static int handle_iio_buffer(state_t *state);
#if GENERATE_STATS
static int handle_stats_timer(state_t *state);
#endif
static usb_buf_t *alloc_usb_buffer(size_t size, int usb_fd, int event_fd);
static void cleanup_state(state_t *state);
static void record_fatal_error(
	state_t *state,
	spf_error_subsystem_t subsystem,
	int error_number);

/* Public functions */
void *THREAD_READ_Entrypoint(void *args)
{
	THREAD_READ_Args_t *thread_args = (THREAD_READ_Args_t*)args;

	/* Enter */
	DEBUG_PRINT("Read thread enter\n");

	/* Set name, priority and CPU affinity */
	pthread_setname_np(pthread_self(), "USB_SDR_GAD_RD");
	UTILS_SetThreadRealtimePriority();
	UTILS_SetThreadAffinity(0);

	/* Reset state */
	state_t state;
	memset(&state, 0x00, sizeof(state));
	state.epoll_fd = -1;
	state.iio_poll_fd = -1;
	state.aio_eventfd = -1;
	#if GENERATE_STATS
	state.stats_timerfd = -1;
	#endif

	/* Store args */
	state.thread_args = thread_args;
	spf_runtime_status_heartbeat(thread_args->runtime_status);

	/* Create epoll instance */
	int epoll_fd = epoll_create1(0);
	if (epoll_fd < 0)
	{
		perror("Failed to create epoll instance");
		goto cleanup;
	}
	else
	{
		DEBUG_PRINT("Opened epoll :-)\n");
	}
	state.epoll_fd = epoll_fd;
	state.acquired_resources |= SPF_RX_RESOURCE_EPOLL;

	struct epoll_event epoll_event;

	/* Register thread quit eventfd with epoll */
	epoll_event.events = EPOLLIN;
	epoll_event.data.ptr = handle_eventfd_thread;
	if (epoll_ctl(epoll_fd, EPOLL_CTL_ADD, thread_args->quit_event_fd, &epoll_event) < 0)
	{
		perror("Failed to register thread quit eventfd with epoll");
		goto cleanup;
	}
	else
	{
		DEBUG_PRINT("Registered thread quit eventfd with with epoll :-)\n");
	}

	/* Create IIO context */
	state.iio_ctx = iio_create_local_context();
	if (!state.iio_ctx)
	{
		fprintf(stderr, "Failed to open iio\n");
		goto cleanup;
	}
	state.acquired_resources |= SPF_RX_RESOURCE_IIO_CONTEXT;

	/* Retrieve RX streaming device */
	struct iio_device *iio_dev_rx = iio_context_find_device(state.iio_ctx, "cf-ad9361-lpc");
	if (!iio_dev_rx)
	{
		fprintf(stderr, "Failed to open iio rx dev\n");
		goto cleanup;
	}

	state.iio_dev_phy = iio_context_find_device(state.iio_ctx, "ad9361-phy");
	if (!state.iio_dev_phy)
	{
		fprintf(stderr, "Failed to open ad9361-phy\n");
		goto cleanup;
	}

	/* Disable all channels */
	unsigned int nb_channels = iio_device_get_channels_count(iio_dev_rx);
	for (unsigned int i = 0; i < nb_channels; i++)
	{
		iio_channel_disable(iio_device_get_channel(iio_dev_rx, i));
	}

	/* Enable required channels */
	for (unsigned int i = 0; i < 32; i++)
	{
		/* Enable channel if required */
		if (thread_args->iio_channels & (1U << i))
		{
			/* Retrieve channel */
			struct iio_channel *channel = iio_device_get_channel(iio_dev_rx, i);
			if (!channel)
			{
				fprintf(stderr, "Failed to find iio rx chan %u\n", i);
				goto cleanup;
			}

			/* Enable channels */
			iio_channel_enable(channel);
		}
	}

	/* Create non-cyclic buffer */
	state.iio_rx_buffer = iio_device_create_buffer(iio_dev_rx, thread_args->iio_buffer_size, false);
	if (!state.iio_rx_buffer)
	{
		fprintf(stderr, "Failed to create rx buffer for %zu samples\n", thread_args->iio_buffer_size);
		goto cleanup;
	}
	state.acquired_resources |= SPF_RX_RESOURCE_IIO_BUFFER;

	/* Register buffer with epoll */
	epoll_event.events = EPOLLIN;
	epoll_event.data.ptr = handle_iio_buffer;
	state.iio_poll_fd = iio_buffer_get_poll_fd(state.iio_rx_buffer);
	if (epoll_ctl(epoll_fd, EPOLL_CTL_ADD, state.iio_poll_fd, &epoll_event) < 0)
	{
		/* Failed to register IIO buffer with epoll */
		perror("Failed to register IIO buffer with epoll");
		goto cleanup;
	}
	else
	{
		state.iio_poll_registered = true;
		DEBUG_PRINT("Registered IIO buffer with with epoll :-)\n");
	}

	/* Retrieve number of bytes between two samples of the same channel (aka size of one sample of all enabled channels) */
	size_t sample_size = iio_buffer_step(state.iio_rx_buffer);

	/* Calculate IQ and USB transfer sizes. */
	state.iq_payload_size = sample_size * thread_args->iio_buffer_size;
	state.metadata_enabled =
		(thread_args->protocol_version == SPF_GAIN_META_VERSION_V1 ||
		 thread_args->protocol_version == SPF_GAIN_META_VERSION_V2);
	state.metadata_v2 =
		(thread_args->protocol_version == SPF_GAIN_META_VERSION_V2);
	state.metadata_header_size = state.metadata_v2
		? sizeof(spf_radio_meta_v2_t)
		: (state.metadata_enabled ? sizeof(spf_gain_meta_v1_t) : 0);
	state.frames_remaining = thread_args->frame_count;
	state.buffer_sequence = 0;
	state.usb_buffer_size =
		state.iq_payload_size + state.metadata_header_size;
	state.buffer_count = spf_usb_buffer_count(
		state.metadata_enabled,
		state.frames_remaining);

	if (state.metadata_enabled &&
		(sample_size != 8 ||
		 thread_args->iio_channels != UINT32_C(0x0F) ||
		 state.frames_remaining == 0))
	{
		fprintf(stderr,
			"Invalid versioned RX layout: step=%zu mask=0x%08x frames=%u\n",
			sample_size,
			thread_args->iio_channels,
			state.frames_remaining);
		goto cleanup;
	}

	if (state.metadata_enabled)
	{
		state.full_gain_table_mode =
			spf_gain_is_full_table_mode(state.iio_dev_phy);
		state.digital_gain_disabled =
			spf_gain_is_digital_gain_disabled(state.iio_dev_phy);
		if (state.metadata_v2)
		{
			if (!state.full_gain_table_mode ||
				!state.digital_gain_disabled ||
				!spf_gain_table_load(
					state.iio_dev_phy,
					&state.gain_table))
			{
				fprintf(stderr,
					"Direct RX v2 requires a valid full gain table and disabled digital gain\n");
				goto cleanup;
			}
			state.previous_gain = spf_gain_read_db_pair(
				state.iio_dev_phy,
				&state.gain_table);
			state.previous_rssi =
				spf_rssi_read_pair(state.iio_dev_phy);
			if (!state.previous_rssi.valid)
			{
				state.rssi_read_failures++;
				spf_runtime_status_increment(
					thread_args->runtime_status,
					SPF_STATUS_COUNTER_RSSI_READ_FAILURE);
			}
		}
		else
		{
			state.previous_gain =
				spf_gain_read_pair(state.iio_dev_phy);
		}
		if (!state.full_gain_table_mode ||
			(state.metadata_v2 && !state.digital_gain_disabled))
		{
			fprintf(stderr,
				"Direct RX gain metadata requires full-table mode with digital gain disabled for v2\n");
			state.previous_gain.valid = false;
			state.previous_gain.rx1 = SPF_GAIN_INDEX_INVALID;
			state.previous_gain.rx2 = SPF_GAIN_INDEX_INVALID;
			state.previous_gain.rx1_db = SPF_GAIN_DB_INVALID;
			state.previous_gain.rx2_db = SPF_GAIN_DB_INVALID;
		}
		if (!state.previous_gain.valid)
		{
			state.gain_read_failures++;
			spf_runtime_status_increment(
				thread_args->runtime_status,
				SPF_STATUS_COUNTER_GAIN_READ_FAILURE);
		}
		DEBUG_PRINT(
			"Initial gains RX1=%u/%d dB RX2=%u/%d dB valid=%d full-table=%d duration=%u ns\n",
			state.previous_gain.rx1,
			state.previous_gain.rx1_db,
			state.previous_gain.rx2,
			state.previous_gain.rx2_db,
			state.previous_gain.valid,
			state.full_gain_table_mode,
			state.previous_gain.duration_ns);
		if (state.metadata_v2)
		{
			DEBUG_PRINT(
				"Initial RSSI RX1=%u qdB RX2=%u qdB valid=%d duration=%u ns table-hash=%08x\n",
				state.previous_rssi.rx1_qdb,
				state.previous_rssi.rx2_qdb,
				state.previous_rssi.valid,
				state.previous_rssi.duration_ns,
				state.gain_table.fnv1a32);
		}
	}

	/* Summarize info */
	DEBUG_PRINT("RX sample count: %zu, iio sample size: %zu, IQ bytes: %zu, USB bytes: %zu, frames: %u, USB buffers: %u\n",
				thread_args->iio_buffer_size,
				sample_size,
				state.iq_payload_size,
				state.usb_buffer_size,
				state.frames_remaining,
				state.buffer_count);

	/* Reset AIO context */
	memset(&state.io_ctx, 0x00, sizeof(state.io_ctx));

	/* Setup AIO context */
	if (io_setup(state.buffer_count, &state.io_ctx) < 0)
	{
		perror("Failed to setup AIO");
		goto cleanup;
	}
	else
	{
		DEBUG_PRINT("Setup AIO :-)\n");
	}
	state.acquired_resources |= SPF_RX_RESOURCE_AIO_CONTEXT;

	/* Prepare eventfd to notify of completed AIO transfers */
	state.aio_eventfd = eventfd(0, 0);
	if (state.aio_eventfd < 0)
	{
		perror("Failed to open eventfd");
		goto cleanup;
	}
	else
	{
		DEBUG_PRINT("Opened eventfd :-)\n");
	}
	state.acquired_resources |= SPF_RX_RESOURCE_AIO_EVENTFD;

	/* Register aio eventfd with epoll */
	epoll_event.events = EPOLLIN;
	epoll_event.data.ptr = handle_eventfd_aio;
	if (epoll_ctl(epoll_fd, EPOLL_CTL_ADD, state.aio_eventfd, &epoll_event) < 0)
	{
		/* Failed to register aio completion eventfd with epoll */
		perror("Failed to register aio completion eventfd with epoll");
		goto cleanup;
	}
	else
	{
		DEBUG_PRINT("Registered aio completion eventfd with with epoll :-)\n");
	}

	/* Init ring buffer */
	RING_BUFFER_Init(&state.ring_buf_ctx, state.buffer_count);

	/* Allocate buffers */
	for (uint32_t i = 0; i < state.buffer_count; i++)
	{
		/* Allocate buffer */
		usb_buf_t *buf = alloc_usb_buffer(state.usb_buffer_size, thread_args->output_fd, state.aio_eventfd);
		if (!buf)
		{
			goto cleanup;
		}

		/* Store buffer */
		state.buffers[i] = buf;
		state.buffers_allocated++;
		state.acquired_resources |= SPF_RX_RESOURCE_USB_BUFFERS;

		/* Push buffer into unused ring position */
		state.ring_buf_data[RING_BUFFER_Put(&state.ring_buf_ctx)] = buf;
	}

	#if GENERATE_STATS
	/* Create stats reporting timer */
	state.stats_timerfd = timerfd_create(CLOCK_MONOTONIC, 0);
	if (state.stats_timerfd < 0)
	{
		perror("Failed to open timerfd");
		goto cleanup;
	}
	else
	{
		DEBUG_PRINT("Opened timerfd :-)\n");
	}
	state.acquired_resources |= SPF_RX_RESOURCE_STATS_TIMER;
	struct itimerspec timer_period =
	{
		.it_value = { .tv_sec = STATS_PERIOD_SECS, .tv_nsec = 0 },
		.it_interval = { .tv_sec = STATS_PERIOD_SECS, .tv_nsec = 0 }
	};
	if (timerfd_settime(state.stats_timerfd, 0, &timer_period, NULL) < 0)
	{
		perror("Failed to set timerfd");
		goto cleanup;
	}
	else
	{
		DEBUG_PRINT("Set timerfd :-)\n");
	}

	/* Register timer with epoll */
	epoll_event.events = EPOLLIN;
	epoll_event.data.ptr = handle_stats_timer;
	if (epoll_ctl(epoll_fd, EPOLL_CTL_ADD, state.stats_timerfd, &epoll_event) < 0)
	{
		/* Failed to register timer with epoll */
		perror("Failed to register timer eventfd with epoll");
		goto cleanup;
	}
	else
	{
		DEBUG_PRINT("Registered timer with with epoll :-)\n");
	}

	/* Init timer */
	UTILS_ResetTimeStats(&state.read_period);
	UTILS_ResetTimeStats(&state.read_dur);
	#endif

	/* Enter main loop */
	state.worker_ready = true;
	spf_runtime_status_set_state(
		thread_args->runtime_status,
		SPF_RUNTIME_STATE_STREAMING,
		true);
	spf_runtime_status_heartbeat(thread_args->runtime_status);
	DEBUG_PRINT("Enter read loop..\n");
	state.keep_running = true;
	while (state.keep_running)
	{
		if (EPOLL_LOOP_Run(epoll_fd, 30000, &state) < 0)
		{
			/* Epoll failed...bail */
			break;
		}
	}
	DEBUG_PRINT("Exit read loop..\n");
	DEBUG_PRINT("Gain read failures: %" PRIu64 "\n", state.gain_read_failures);
	DEBUG_PRINT("RSSI read failures: %" PRIu64 "\n", state.rssi_read_failures);

cleanup:
	if (!state.worker_ready)
		record_fatal_error(&state, SPF_ERROR_SUBSYSTEM_RX_INIT, errno);
	cleanup_state(&state);
	DEBUG_PRINT("Read thread exit\n");

	return NULL;
}

static void record_fatal_error(
	state_t *state,
	spf_error_subsystem_t subsystem,
	int error_number)
{
	spf_runtime_status_record_error(
		state->thread_args->runtime_status,
		subsystem,
		error_number != 0 ? error_number : EIO);
}

static void cleanup_state(state_t *state)
{
	spf_rx_resource_t resource;
	while ((resource = spf_rx_cleanup_next(state->acquired_resources)) !=
		SPF_RX_RESOURCE_NONE)
	{
		switch (resource)
		{
			case SPF_RX_RESOURCE_STATS_TIMER:
				#if GENERATE_STATS
				if (state->stats_timerfd >= 0)
					close(state->stats_timerfd);
				state->stats_timerfd = -1;
				#endif
				break;
			case SPF_RX_RESOURCE_AIO_CONTEXT:
				/* Cancel pending writes before freeing their backing buffers. */
				io_destroy(state->io_ctx);
				memset(&state->io_ctx, 0, sizeof(state->io_ctx));
				break;
			case SPF_RX_RESOURCE_USB_BUFFERS:
				for (uint32_t index = 0;
					index < state->buffers_allocated;
					++index)
				{
					free(state->buffers[index]);
					state->buffers[index] = NULL;
				}
				state->buffers_allocated = 0;
				break;
			case SPF_RX_RESOURCE_AIO_EVENTFD:
				if (state->aio_eventfd >= 0)
					close(state->aio_eventfd);
				state->aio_eventfd = -1;
				break;
			case SPF_RX_RESOURCE_IIO_BUFFER:
				iio_buffer_destroy(state->iio_rx_buffer);
				state->iio_rx_buffer = NULL;
				break;
			case SPF_RX_RESOURCE_IIO_CONTEXT:
				iio_context_destroy(state->iio_ctx);
				state->iio_ctx = NULL;
				state->iio_dev_phy = NULL;
				break;
			case SPF_RX_RESOURCE_EPOLL:
				if (state->epoll_fd >= 0)
					close(state->epoll_fd);
				state->epoll_fd = -1;
				break;
			case SPF_RX_RESOURCE_NONE:
				break;
		}
		state->acquired_resources &= ~(uint32_t)resource;
	}
}

/* Private functions */
static int handle_eventfd_thread(state_t *state)
{
	spf_runtime_status_heartbeat(state->thread_args->runtime_status);
	/* Quit having detected write on eventfd */
	DEBUG_PRINT("Stop request received\n");
	state->keep_running = false;

	return 0;
}

static int handle_eventfd_aio(state_t *state)
{
	spf_runtime_status_heartbeat(state->thread_args->runtime_status);
	struct io_event events[ARRAY_SIZE(state->buffers)];

	/* Read eventfd to reset it */
	uint64_t dummy;
	if (read(state->aio_eventfd, &dummy, sizeof(dummy)) < 0)
	{
		perror("Failed to read aio completion eventfd");
		return -1;
	}

	/* Read at least one event (having been signalled by eventfd, there should be one pending) but do not block */
	struct timespec timeout = {0, 0};
	int ret = io_getevents(state->io_ctx, 1, ARRAY_SIZE(events), events, &timeout);
	if (ret < 0)
	{
		perror("Failed to read completed io events");
		return -1;
	}

	/* Iterate over events */
	bool completion_failed = false;
	for (int i = 0; i < ret; i++)
	{
		/* Shorthand ptr */
		struct io_event *event = &events[i];
		const long completion_result = (long)event->res;
		const bool completion_ok =
			completion_result >= 0 &&
			state->usb_buffer_size == (size_t)completion_result;

		/* Check for success */
		if (state->usb_buffer_size != (size_t)event->res)
		{
			/* Not all data was written, or write failed, check if failure was down to configuration being disabled */
			if (-ESHUTDOWN != completion_result)
			{
				fprintf(stderr, "USB write completed with error, res: %ld, res2: %ld\n", event->res, event->res2);
				spf_runtime_status_increment(
					state->thread_args->runtime_status,
					SPF_STATUS_COUNTER_SHORT_WRITE);
				record_fatal_error(
					state,
					SPF_ERROR_SUBSYSTEM_USB_COMPLETION,
					completion_result < 0 ? (int)-completion_result : EIO);
				completion_failed = true;
			}
		}

		/* Retrieve buffer */
		usb_buf_t *buf = (usb_buf_t*)event->data;
		if (completion_ok && buf->sequence_valid)
		{
			spf_runtime_status_complete_frame(
				state->thread_args->runtime_status,
				buf->sequence);
			state->frames_completed_in_stream++;
			if (state->metadata_enabled &&
				state->frames_completed_in_stream ==
				state->thread_args->frame_count)
			{
				spf_runtime_status_set_state(
					state->thread_args->runtime_status,
					SPF_RUNTIME_STATE_COMPLETE,
					true);
			}
		}

		/* Mark as unused */
		buf->in_use = false;
		buf->sequence_valid = false;

		/* Return to ring buffer */
		state->ring_buf_data[RING_BUFFER_Put(&state->ring_buf_ctx)] = buf;
	}

	return completion_failed ? -1 : 0;
}

static int handle_iio_buffer(state_t *state)
{
	spf_runtime_status_heartbeat(state->thread_args->runtime_status);
	#if GENERATE_STATS
	/* Capture read period */
	UTILS_UpdateTimeStats(&state->read_period);

	/* Record read start time */
	UTILS_StartTimeStats(&state->read_dur);
	#endif

	/* Refill buffer */
	ssize_t nbytes = iio_buffer_refill(state->iio_rx_buffer);
	if (nbytes != (ssize_t)state->iq_payload_size)
	{
		fprintf(stderr, "RX buffer read failed, expected %zu, read %zd bytes\n", state->iq_payload_size, nbytes);
		spf_runtime_status_increment(
			state->thread_args->runtime_status,
			SPF_STATUS_COUNTER_IIO_REFILL_ERROR);
		record_fatal_error(
			state,
			SPF_ERROR_SUBSYSTEM_IIO_REFILL,
			nbytes < 0 ? (int)-nbytes : EIO);
		return -1;
	}

	spf_gain_pair_t current_gain = {
		.rx1 = SPF_GAIN_INDEX_INVALID,
		.rx2 = SPF_GAIN_INDEX_INVALID,
		.rx1_db = SPF_GAIN_DB_INVALID,
		.rx2_db = SPF_GAIN_DB_INVALID,
		.valid = false,
		.duration_ns = 0,
	};
	spf_rssi_pair_t current_rssi = {
		.rx1_qdb = SPF_RSSI_QDB_INVALID,
		.rx2_qdb = SPF_RSSI_QDB_INVALID,
		.valid = false,
		.duration_ns = 0,
	};
	uint64_t this_buffer_sequence = state->buffer_sequence;
	if (state->metadata_enabled)
	{
		current_gain = state->metadata_v2
			? spf_gain_read_db_pair(
				state->iio_dev_phy,
				&state->gain_table)
			: spf_gain_read_pair(state->iio_dev_phy);
		if (!state->full_gain_table_mode)
		{
			current_gain.valid = false;
			current_gain.rx1 = SPF_GAIN_INDEX_INVALID;
			current_gain.rx2 = SPF_GAIN_INDEX_INVALID;
		}
		if (!current_gain.valid)
		{
			state->gain_read_failures++;
			spf_runtime_status_increment(
				state->thread_args->runtime_status,
				SPF_STATUS_COUNTER_GAIN_READ_FAILURE);
		}
		if (state->metadata_v2)
		{
			current_rssi = spf_rssi_read_pair(state->iio_dev_phy);
			if (!current_rssi.valid)
			{
				state->rssi_read_failures++;
				spf_runtime_status_increment(
					state->thread_args->runtime_status,
					SPF_STATUS_COUNTER_RSSI_READ_FAILURE);
			}
		}
		this_buffer_sequence = state->buffer_sequence++;
	}

	#if GENERATE_STATS
	/* Capture read end time */
	UTILS_UpdateTimeStats(&state->read_dur);

	/* Record period start time (to subtract read time above) */
	UTILS_StartTimeStats(&state->read_period);
	#endif

	/* Retrieve free buffer */
	uint32_t index = RING_BUFFER_Get(&state->ring_buf_ctx);
	if (RING_BUFFER_NO_INDEX != index)
	{
		/* Retrieve ptr to buffer */
		usb_buf_t *buf = state->ring_buf_data[index];

		/* Mark in use */
		buf->in_use = true;

		uint8_t *iq_destination = buf->data;
		if (state->metadata_enabled)
		{
			uint32_t common_flags = SPF_META_SAMPLE_SEQUENCE_VALID;
			if (state->previous_gain.valid)
				common_flags |= SPF_META_START_VALID;
			if (current_gain.valid)
				common_flags |= SPF_META_END_VALID;
			if (!state->previous_gain.valid || !current_gain.valid)
				common_flags |= SPF_META_GAIN_READ_FAILED;
			if (state->full_gain_table_mode)
				common_flags |= SPF_META_GAIN_FULL_TABLE_MODE;
			if (state->previous_gain.valid && current_gain.valid)
			{
				if (state->previous_gain.rx1 != current_gain.rx1)
					common_flags |= SPF_META_RX1_ENDPOINT_CHANGED;
				if (state->previous_gain.rx2 != current_gain.rx2)
					common_flags |= SPF_META_RX2_ENDPOINT_CHANGED;
			}
			if (state->overflow_seen)
				common_flags |= SPF_META_DEVICE_IIO_OVERFLOW;

			if (state->metadata_v2)
			{
				spf_radio_meta_v2_t *header =
					(spf_radio_meta_v2_t *)buf->data;
				memset(header, 0, sizeof(*header));
				header->magic = SPF_GAIN_META_MAGIC;
				header->version = SPF_GAIN_META_VERSION_V2;
				header->header_bytes = SPF_GAIN_META_HEADER_BYTES_V2;
				header->features = state->thread_args->metadata_features;
				header->flags =
					common_flags | SPF_META_GAIN_DB_VALUES;
				if (state->previous_rssi.valid)
					header->flags |= SPF_META_RSSI_START_VALID;
				if (current_rssi.valid)
					header->flags |= SPF_META_RSSI_END_VALID;
				if (!state->previous_rssi.valid || !current_rssi.valid)
					header->flags |= SPF_META_RSSI_READ_FAILED;
				header->stream_id = state->thread_args->stream_id;
				header->buffer_sequence = this_buffer_sequence;
				header->first_sample_sequence =
					this_buffer_sequence * state->thread_args->iio_buffer_size;
				header->samples_per_channel =
					(uint32_t)state->thread_args->iio_buffer_size;
				header->iq_payload_bytes =
					(uint32_t)state->iq_payload_size;
				header->enabled_scan_mask =
					state->thread_args->iio_channels;
				header->sample_format =
					SPF_SAMPLE_FORMAT_CS16_LE_TIME_INTERLEAVED;
				header->channel_count = 2;
				header->rx1_gain_db_start =
					state->previous_gain.rx1_db;
				header->rx2_gain_db_start =
					state->previous_gain.rx2_db;
				header->rx1_gain_db_end = current_gain.rx1_db;
				header->rx2_gain_db_end = current_gain.rx2_db;
				header->gain_start_read_duration_ns =
					state->previous_gain.duration_ns;
				header->gain_end_read_duration_ns =
					current_gain.duration_ns;
				header->rx1_first_change_sample =
					SPF_FIRST_CHANGE_UNAVAILABLE;
				header->rx2_first_change_sample =
					SPF_FIRST_CHANGE_UNAVAILABLE;
				header->rx1_rssi_start_qdb =
					state->previous_rssi.rx1_qdb;
				header->rx2_rssi_start_qdb =
					state->previous_rssi.rx2_qdb;
				header->rx1_rssi_end_qdb =
					current_rssi.rx1_qdb;
				header->rx2_rssi_end_qdb =
					current_rssi.rx2_qdb;
				header->rssi_start_read_duration_ns =
					state->previous_rssi.duration_ns;
				header->rssi_end_read_duration_ns =
					current_rssi.duration_ns;
				header->header_crc32 = 0;
				header->header_crc32 =
					spf_gain_meta_crc32(header, sizeof(*header));
				iq_destination += sizeof(*header);
			}
			else
			{
				spf_gain_meta_v1_t *header =
					(spf_gain_meta_v1_t *)buf->data;
				memset(header, 0, sizeof(*header));
				header->magic = SPF_GAIN_META_MAGIC;
				header->version = SPF_GAIN_META_VERSION_V1;
				header->header_bytes = SPF_GAIN_META_HEADER_BYTES_V1;
				header->features = state->thread_args->metadata_features;
				header->flags = common_flags;
				header->stream_id = state->thread_args->stream_id;
				header->buffer_sequence = this_buffer_sequence;
				header->first_sample_sequence =
					this_buffer_sequence * state->thread_args->iio_buffer_size;
				header->samples_per_channel =
					(uint32_t)state->thread_args->iio_buffer_size;
				header->iq_payload_bytes =
					(uint32_t)state->iq_payload_size;
				header->enabled_scan_mask =
					state->thread_args->iio_channels;
				header->sample_format =
					SPF_SAMPLE_FORMAT_CS16_LE_TIME_INTERLEAVED;
				header->channel_count = 2;
				header->rx1_gain_start = state->previous_gain.rx1;
				header->rx2_gain_start = state->previous_gain.rx2;
				header->rx1_gain_end = current_gain.rx1;
				header->rx2_gain_end = current_gain.rx2;
				header->gain_start_read_duration_ns =
					state->previous_gain.duration_ns;
				header->gain_end_read_duration_ns =
					current_gain.duration_ns;
				header->rx1_first_change_sample =
					SPF_FIRST_CHANGE_UNAVAILABLE;
				header->rx2_first_change_sample =
					SPF_FIRST_CHANGE_UNAVAILABLE;
				header->header_crc32 = 0;
				header->header_crc32 =
					spf_gain_meta_crc32(header, sizeof(*header));
				iq_destination += sizeof(*header);
			}
			state->overflow_seen = false;
		}

		/* Copy IQ immediately after the optional metadata header. */
		memcpy(iq_destination,
			iio_buffer_start(state->iio_rx_buffer),
			state->iq_payload_size);

		/* Submit request */
		buf->sequence = this_buffer_sequence;
		buf->sequence_valid = state->metadata_enabled;
		struct iocb *iocb = &buf->iocb;
		int res = io_submit(state->io_ctx, 1, &iocb);
		if (1 != res)
		{
			/* Failed to submit context */
			perror("Failed to submit usb write");
			buf->in_use = false;
			buf->sequence_valid = false;
			spf_runtime_status_increment(
				state->thread_args->runtime_status,
				SPF_STATUS_COUNTER_USB_SUBMIT_ERROR);
			record_fatal_error(
				state,
				SPF_ERROR_SUBSYSTEM_USB_SUBMIT,
				errno);
			return -1;
		}

		if (state->metadata_enabled)
		{
			state->frames_remaining--;
			if (state->frames_remaining == 0 && state->iio_poll_registered)
			{
				if (epoll_ctl(
						state->epoll_fd,
						EPOLL_CTL_DEL,
						state->iio_poll_fd,
						NULL) < 0)
				{
					perror("Failed to stop finite IIO capture");
					return -1;
				}
				state->iio_poll_registered = false;
				DEBUG_PRINT("Finite RX capture complete\n");
			}
		}
	}
	else
	{
		if (state->metadata_enabled)
			state->overflow_seen = true;
		spf_runtime_status_increment(
			state->thread_args->runtime_status,
			SPF_STATUS_COUNTER_BUFFER_STARVATION);
		spf_runtime_status_increment(
			state->thread_args->runtime_status,
			SPF_STATUS_COUNTER_DROPPED_FRAME);
		#if GENERATE_STATS
		/* Count overflow */
		state->overflows++;
		#endif
	}

	if (state->metadata_enabled)
	{
		state->previous_gain = current_gain;
		if (state->metadata_v2)
			state->previous_rssi = current_rssi;
	}

	return 0;
}

#if GENERATE_STATS
static int handle_stats_timer(state_t *state)
{
	/* Read timer to acknowledge it */
	uint64_t timerfd_val;
	if (read(state->stats_timerfd, &timerfd_val, sizeof(timerfd_val)) < 0)
	{
		perror("Failed to read timerfd");
		return 1;
	}

	/* Report min/max/average read period */
	printf("Read period: min: %"PRIu64", max: %"PRIu64", avg: %"PRIu64" (uS)\n",
		   state->read_period.min,
		   state->read_period.max,
		   UTILS_CalcAverageTimeStats(&state->read_period)
	);

	/* Report min/max/average read duration */
	printf("Read dur: min: %"PRIu64", max: %"PRIu64", avg: %"PRIu64" (uS)\n",
		   state->read_dur.min,
		   state->read_dur.max,
		   UTILS_CalcAverageTimeStats(&state->read_dur)
	);

	/* Check for overflows */
	if (state->overflows > 0)
	{
		printf("Read overflows: %u in last 5s period\n", state->overflows);
	}

	/* Reset stats */
	UTILS_ResetTimeStats(&state->read_period);
	UTILS_ResetTimeStats(&state->read_dur);
	state->overflows = 0;

	return 0;
}
#endif

static usb_buf_t *alloc_usb_buffer(size_t size, int usb_fd, int event_fd)
{
	usb_buf_t *buf;

	/* Allocate struct + data data */
	buf = malloc(sizeof(usb_buf_t) + size);
	if (!buf)
	{
		perror("alloc_buffer failed");
		return NULL;
	}

	/* Reset in-use flag */
	buf->in_use = false;

	/* Prepare request */
	io_prep_pwrite(&buf->iocb, usb_fd, buf->data, size, 0);

	/* Set data to point at buffer such that we can find the buffer on io completion */
	buf->iocb.data = buf;

	/* Enable eventfd notification of completion */
	io_set_eventfd(&buf->iocb, event_fd);

	return buf;
}
