#include "spf_runtime_status.h"

#include <assert.h>
#include <string.h>

int main(void)
{
	uint8_t boot_id[16];
	uint8_t process_nonce[16];
	memset(boot_id, 0x11, sizeof(boot_id));
	memset(process_nonce, 0x22, sizeof(process_nonce));
	spf_runtime_status_t runtime;
	assert(spf_runtime_status_init(&runtime, boot_id, process_nonce));

	spf_runtime_status_set_stream(&runtime, UINT64_C(0x0102030405060708));
	spf_runtime_status_increment(&runtime, SPF_STATUS_COUNTER_START);
	spf_runtime_status_set_state(&runtime, SPF_RUNTIME_STATE_STREAMING, true);
	spf_runtime_status_complete_frame(&runtime, 7);
	spf_runtime_status_increment(&runtime, SPF_STATUS_COUNTER_GAIN_READ_FAILURE);
	spf_runtime_status_record_error(
		&runtime,
		SPF_ERROR_SUBSYSTEM_IIO_REFILL,
		5);

	cmd_usb_runtime_status_v1_t snapshot;
	spf_runtime_status_snapshot(&runtime, &snapshot);
	assert(snapshot.magic == SPF_RUNTIME_STATUS_MAGIC);
	assert(snapshot.response_bytes == 128);
	assert(snapshot.version == 1);
	assert(snapshot.lifecycle_state == SPF_RUNTIME_STATE_FAILED);
	assert(snapshot.last_error_subsystem == SPF_ERROR_SUBSYSTEM_IIO_REFILL);
	assert(snapshot.last_errno == 5);
	assert(snapshot.flags & SPF_RUNTIME_STATUS_FLAG_BOOT_ID_VALID);
	assert(snapshot.flags & SPF_RUNTIME_STATUS_FLAG_PROCESS_NONCE_VALID);
	assert(snapshot.flags & SPF_RUNTIME_STATUS_FLAG_RX_WORKER_ACTIVE);
	assert(memcmp(snapshot.boot_id, boot_id, 16) == 0);
	assert(memcmp(snapshot.process_nonce, process_nonce, 16) == 0);
	assert(snapshot.current_stream_id == UINT64_C(0x0102030405060708));
	assert(snapshot.last_completed_sequence == 7);
	assert(snapshot.start_count == 1);
	assert(snapshot.completed_frame_count == 1);
	assert(snapshot.gain_read_failure_count == 1);
	assert(snapshot.iio_refill_error_count == 0);

	spf_runtime_status_destroy(&runtime);
	return 0;
}
