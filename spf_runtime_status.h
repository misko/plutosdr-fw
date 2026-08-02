#ifndef __SPF_RUNTIME_STATUS_H__
#define __SPF_RUNTIME_STATUS_H__

#include <pthread.h>
#include <stdbool.h>
#include <stdint.h>
#include <time.h>

#include "sdr_usb_gadget_types.h"

typedef enum
{
	SPF_STATUS_COUNTER_START,
	SPF_STATUS_COUNTER_STOP,
	SPF_STATUS_COUNTER_COMPLETED_FRAME,
	SPF_STATUS_COUNTER_DROPPED_FRAME,
	SPF_STATUS_COUNTER_IIO_REFILL_ERROR,
	SPF_STATUS_COUNTER_USB_SUBMIT_ERROR,
	SPF_STATUS_COUNTER_SHORT_WRITE,
	SPF_STATUS_COUNTER_BUFFER_STARVATION,
	SPF_STATUS_COUNTER_GAIN_READ_FAILURE,
	SPF_STATUS_COUNTER_RSSI_READ_FAILURE,
	SPF_STATUS_COUNTER_CONTROL_ERROR,
	SPF_STATUS_COUNTER_STOP_TIMEOUT,
} spf_status_counter_t;

typedef struct
{
	pthread_mutex_t mutex;
	cmd_usb_runtime_status_v1_t wire;
	struct timespec last_worker_heartbeat;
} spf_runtime_status_t;

bool spf_runtime_status_init(
	spf_runtime_status_t *status,
	const uint8_t boot_id[16],
	const uint8_t process_nonce[16]);
bool spf_runtime_status_init_auto(spf_runtime_status_t *status);
void spf_runtime_status_destroy(spf_runtime_status_t *status);
void spf_runtime_status_snapshot(
	spf_runtime_status_t *status,
	cmd_usb_runtime_status_v1_t *snapshot);
void spf_runtime_status_set_state(
	spf_runtime_status_t *status,
	spf_runtime_state_t state,
	bool worker_active);
void spf_runtime_status_set_stream(
	spf_runtime_status_t *status,
	uint64_t stream_id);
void spf_runtime_status_record_error(
	spf_runtime_status_t *status,
	spf_error_subsystem_t subsystem,
	int error_number);
void spf_runtime_status_note_error(
	spf_runtime_status_t *status,
	spf_error_subsystem_t subsystem,
	int error_number);
void spf_runtime_status_increment(
	spf_runtime_status_t *status,
	spf_status_counter_t counter);
void spf_runtime_status_complete_frame(
	spf_runtime_status_t *status,
	uint64_t sequence);
void spf_runtime_status_heartbeat(spf_runtime_status_t *status);

#endif
