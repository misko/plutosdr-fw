#ifndef __THREAD_READ_H__
#define __THREAD_READ_H__

/* Standard libraries */
#include <stdint.h>
#include <stddef.h>

#include "spf_runtime_status.h"

/* Type definitions - thread args */
typedef struct
{
	/* Eventfd used to signal thread to quit */
	int quit_event_fd;

	/* USB endpoint to write to */
	int output_fd;

	/* Enabled channels */
	uint32_t iio_channels;

	/* Sample buffer size (in samples) */
	size_t iio_buffer_size;

	/* Zero for the legacy unbounded IQ-only transport. */
	uint16_t protocol_version;

	/* Negotiated metadata feature mask. */
	uint32_t metadata_features;

	/* Zero for unbounded legacy streaming, otherwise a finite frame count. */
	uint32_t frame_count;

	/* Nonzero ID generated for every versioned START. */
	uint64_t stream_id;

	/* Process-wide status shared with the USB control thread. */
	spf_runtime_status_t *runtime_status;

} THREAD_READ_Args_t;

/* Public functions - Thread entrypoint */
void *THREAD_READ_Entrypoint(void *args);

#endif
