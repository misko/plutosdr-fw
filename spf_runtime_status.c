#include "spf_runtime_status.h"

#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

static uint32_t elapsed_ms(struct timespec before, struct timespec after)
{
	int64_t seconds = (int64_t)after.tv_sec - (int64_t)before.tv_sec;
	int64_t nanoseconds = (int64_t)after.tv_nsec - (int64_t)before.tv_nsec;
	int64_t total = seconds * INT64_C(1000) + nanoseconds / INT64_C(1000000);
	if (total <= 0)
		return 0;
	if (total > UINT32_MAX)
		return UINT32_MAX;
	return (uint32_t)total;
}

static bool parse_uuid(const char *text, uint8_t output[16])
{
	unsigned int nibble_count = 0;
	uint8_t value = 0;
	memset(output, 0, 16);
	for (const char *cursor = text; *cursor != '\0' && *cursor != '\n'; ++cursor)
	{
		if (*cursor == '-')
			continue;
		unsigned int nibble;
		if (*cursor >= '0' && *cursor <= '9')
			nibble = (unsigned int)(*cursor - '0');
		else if (*cursor >= 'a' && *cursor <= 'f')
			nibble = (unsigned int)(*cursor - 'a') + 10U;
		else if (*cursor >= 'A' && *cursor <= 'F')
			nibble = (unsigned int)(*cursor - 'A') + 10U;
		else
			return false;
		value = (uint8_t)((value << 4) | nibble);
		if ((nibble_count & 1U) != 0)
		{
			if (nibble_count / 2U >= 16U)
				return false;
			output[nibble_count / 2U] = value;
			value = 0;
		}
		nibble_count++;
	}
	return nibble_count == 32U;
}

static bool read_boot_id(uint8_t output[16])
{
	char text[64] = {0};
	FILE *input = fopen("/proc/sys/kernel/random/boot_id", "r");
	if (!input)
		return false;
	const bool read_ok = fgets(text, sizeof(text), input) != NULL;
	fclose(input);
	return read_ok && parse_uuid(text, output);
}

static bool read_process_nonce(uint8_t output[16])
{
	int fd = open("/dev/urandom", O_RDONLY | O_CLOEXEC);
	if (fd < 0)
		return false;
	size_t offset = 0;
	while (offset < 16U)
	{
		ssize_t count = read(fd, output + offset, 16U - offset);
		if (count < 0 && errno == EINTR)
			continue;
		if (count <= 0)
			break;
		offset += (size_t)count;
	}
	close(fd);
	return offset == 16U;
}

bool spf_runtime_status_init(
	spf_runtime_status_t *status,
	const uint8_t boot_id[16],
	const uint8_t process_nonce[16])
{
	memset(status, 0, sizeof(*status));
	if (pthread_mutex_init(&status->mutex, NULL) != 0)
		return false;
	status->wire.magic = SPF_RUNTIME_STATUS_MAGIC;
	status->wire.response_bytes = sizeof(status->wire);
	status->wire.version = SPF_RUNTIME_STATUS_VERSION;
	status->wire.lifecycle_state = SPF_RUNTIME_STATE_IDLE;
	status->wire.last_completed_sequence = UINT64_MAX;
	if (boot_id)
	{
		memcpy(status->wire.boot_id, boot_id, 16);
		status->wire.flags |= SPF_RUNTIME_STATUS_FLAG_BOOT_ID_VALID;
	}
	if (process_nonce)
	{
		memcpy(status->wire.process_nonce, process_nonce, 16);
		status->wire.flags |= SPF_RUNTIME_STATUS_FLAG_PROCESS_NONCE_VALID;
	}
	clock_gettime(CLOCK_MONOTONIC, &status->last_worker_heartbeat);
	return true;
}

bool spf_runtime_status_init_auto(spf_runtime_status_t *status)
{
	uint8_t boot_id[16] = {0};
	uint8_t process_nonce[16] = {0};
	const bool boot_valid = read_boot_id(boot_id);
	const bool nonce_valid = read_process_nonce(process_nonce);
	return spf_runtime_status_init(
		status,
		boot_valid ? boot_id : NULL,
		nonce_valid ? process_nonce : NULL);
}

void spf_runtime_status_destroy(spf_runtime_status_t *status)
{
	pthread_mutex_destroy(&status->mutex);
}

void spf_runtime_status_snapshot(
	spf_runtime_status_t *status,
	cmd_usb_runtime_status_v1_t *snapshot)
{
	struct timespec now = {0, 0};
	clock_gettime(CLOCK_MONOTONIC, &now);
	pthread_mutex_lock(&status->mutex);
	*snapshot = status->wire;
	if (snapshot->flags & SPF_RUNTIME_STATUS_FLAG_RX_WORKER_ACTIVE)
	{
		snapshot->worker_heartbeat_age_ms =
			elapsed_ms(status->last_worker_heartbeat, now);
	}
	else
	{
		snapshot->worker_heartbeat_age_ms = 0;
	}
	pthread_mutex_unlock(&status->mutex);
}

void spf_runtime_status_set_state(
	spf_runtime_status_t *status,
	spf_runtime_state_t state,
	bool worker_active)
{
	pthread_mutex_lock(&status->mutex);
	status->wire.lifecycle_state = (uint16_t)state;
	if (worker_active)
		status->wire.flags |= SPF_RUNTIME_STATUS_FLAG_RX_WORKER_ACTIVE;
	else
		status->wire.flags &= ~SPF_RUNTIME_STATUS_FLAG_RX_WORKER_ACTIVE;
	pthread_mutex_unlock(&status->mutex);
}

void spf_runtime_status_set_stream(
	spf_runtime_status_t *status,
	uint64_t stream_id)
{
	pthread_mutex_lock(&status->mutex);
	status->wire.current_stream_id = stream_id;
	status->wire.last_completed_sequence = UINT64_MAX;
	pthread_mutex_unlock(&status->mutex);
}

void spf_runtime_status_record_error(
	spf_runtime_status_t *status,
	spf_error_subsystem_t subsystem,
	int error_number)
{
	spf_runtime_status_note_error(status, subsystem, error_number);
	pthread_mutex_lock(&status->mutex);
	status->wire.lifecycle_state = SPF_RUNTIME_STATE_FAILED;
	pthread_mutex_unlock(&status->mutex);
}

void spf_runtime_status_note_error(
	spf_runtime_status_t *status,
	spf_error_subsystem_t subsystem,
	int error_number)
{
	pthread_mutex_lock(&status->mutex);
	status->wire.last_error_subsystem = (uint16_t)subsystem;
	status->wire.last_errno = error_number;
	pthread_mutex_unlock(&status->mutex);
}

void spf_runtime_status_increment(
	spf_runtime_status_t *status,
	spf_status_counter_t counter)
{
	pthread_mutex_lock(&status->mutex);
	switch (counter)
	{
		case SPF_STATUS_COUNTER_START: status->wire.start_count++; break;
		case SPF_STATUS_COUNTER_STOP: status->wire.stop_count++; break;
		case SPF_STATUS_COUNTER_COMPLETED_FRAME: status->wire.completed_frame_count++; break;
		case SPF_STATUS_COUNTER_DROPPED_FRAME: status->wire.dropped_frame_count++; break;
		case SPF_STATUS_COUNTER_IIO_REFILL_ERROR: status->wire.iio_refill_error_count++; break;
		case SPF_STATUS_COUNTER_USB_SUBMIT_ERROR: status->wire.usb_submit_error_count++; break;
		case SPF_STATUS_COUNTER_SHORT_WRITE: status->wire.short_write_count++; break;
		case SPF_STATUS_COUNTER_BUFFER_STARVATION: status->wire.buffer_starvation_count++; break;
		case SPF_STATUS_COUNTER_GAIN_READ_FAILURE: status->wire.gain_read_failure_count++; break;
		case SPF_STATUS_COUNTER_RSSI_READ_FAILURE: status->wire.rssi_read_failure_count++; break;
		case SPF_STATUS_COUNTER_CONTROL_ERROR: status->wire.control_error_count++; break;
		case SPF_STATUS_COUNTER_STOP_TIMEOUT: status->wire.stop_timeout_count++; break;
	}
	pthread_mutex_unlock(&status->mutex);
}

void spf_runtime_status_complete_frame(
	spf_runtime_status_t *status,
	uint64_t sequence)
{
	pthread_mutex_lock(&status->mutex);
	status->wire.completed_frame_count++;
	if (status->wire.last_completed_sequence == UINT64_MAX ||
		sequence > status->wire.last_completed_sequence)
	{
		status->wire.last_completed_sequence = sequence;
	}
	pthread_mutex_unlock(&status->mutex);
}

void spf_runtime_status_heartbeat(spf_runtime_status_t *status)
{
	struct timespec now = {0, 0};
	clock_gettime(CLOCK_MONOTONIC, &now);
	pthread_mutex_lock(&status->mutex);
	status->last_worker_heartbeat = now;
	pthread_mutex_unlock(&status->mutex);
}
