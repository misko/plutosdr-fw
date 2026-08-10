#ifndef THREAD_READ_V3_H
#define THREAD_READ_V3_H

#include <netinet/in.h>
#include <stddef.h>
#include <stdint.h>

typedef struct
{
	int quit_event_fd;
	/* Reports 1 after complete initialization, or 2 on startup failure. */
	int startup_event_fd;
	/* Main releases the initialized worker only after STARTED is sent. */
	int run_event_fd;
	/* Reports 1 success, 2 failure, or 3 cancellation after cleanup. */
	int done_event_fd;
	int output_fd;
	struct sockaddr_in addr;
	uint32_t iio_channels;
	size_t samples_per_channel;
	size_t udp_datagram_bytes;
	uint32_t frame_count;
	uint64_t stream_id;
	uint64_t generation;
	uint32_t metadata_features;
	uint32_t gain_observation_interval_samples;
	uint16_t gain_observation_capacity;
	uint16_t gain_event_capacity;
	uint32_t target_payload_bytes_per_second;
	uint32_t pacing_interval_us;
} THREAD_READ_V3_Args_t;

void *THREAD_READ_V3_Entrypoint(void *args);

#endif
