#include "sdr_usb_gadget_types.h"
#include "spf_gain_metadata.h"

#include <stdio.h>
#include <string.h>

static int check_bytes(
	const char *name,
	const void *actual,
	const uint8_t *expected,
	size_t size)
{
	if (memcmp(actual, expected, size) == 0)
		return 0;

	const uint8_t *bytes = (const uint8_t *)actual;
	fprintf(stderr, "%s mismatch\nactual: ", name);
	for (size_t i = 0; i < size; ++i)
		fprintf(stderr, "%02x", bytes[i]);
	fprintf(stderr, "\n");
	return 1;
}

int main(void)
{
	static const uint8_t capabilities_golden[32] = {
		0x53, 0x47, 0x43, 0x50, 0x20, 0x00, 0x01, 0x00,
		0x02, 0x00, 0x00, 0x00, 0x37, 0x00, 0x00, 0x00,
		0x00, 0x00, 0x08, 0x00, 0x10, 0x00, 0x00, 0x00,
		0x0d, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
	};
	const cmd_usb_capabilities_v1_t capabilities = {
		.magic = SPF_GADGET_CAPS_MAGIC,
		.response_bytes = sizeof(cmd_usb_capabilities_v1_t),
		.protocol_min = SPF_GADGET_PROTOCOL_V1,
		.protocol_max = SPF_GADGET_PROTOCOL_V2,
		.supported_features = SPF_META_REQUIRED_FEATURES_V2,
		.max_samples_per_channel = SPF_GADGET_MAX_SAMPLES_PER_CHANNEL,
		.max_finite_frames = SPF_GADGET_MAX_FINITE_FRAMES,
		.capability_flags =
			SPF_GADGET_CAP_FINITE_RX |
			SPF_GADGET_CAP_HARDWARE_IDENTITY |
			SPF_GADGET_CAP_STATUS,
	};

	static const uint8_t status_golden[128] = {
		[0] = 0x53, [1] = 0x53, [2] = 0x54, [3] = 0x31,
		[4] = 0x80, [6] = 0x01,
		[8] = 0x02, [10] = 0x04,
		[12] = 0x05,
		[16] = 0x07,
		[24] = 0x11, [25] = 0x11, [26] = 0x11, [27] = 0x11,
		[28] = 0x11, [29] = 0x11, [30] = 0x11, [31] = 0x11,
		[32] = 0x11, [33] = 0x11, [34] = 0x11, [35] = 0x11,
		[36] = 0x11, [37] = 0x11, [38] = 0x11, [39] = 0x11,
		[40] = 0x22, [41] = 0x22, [42] = 0x22, [43] = 0x22,
		[44] = 0x22, [45] = 0x22, [46] = 0x22, [47] = 0x22,
		[48] = 0x22, [49] = 0x22, [50] = 0x22, [51] = 0x22,
		[52] = 0x22, [53] = 0x22, [54] = 0x22, [55] = 0x22,
		[56] = 0x08, [57] = 0x07, [58] = 0x06, [59] = 0x05,
		[60] = 0x04, [61] = 0x03, [62] = 0x02, [63] = 0x01,
		[64] = 0x09,
		[72] = 0x0a, [76] = 0x0b, [80] = 0x0c, [84] = 0x0d,
		[88] = 0x0e, [92] = 0x0f, [96] = 0x10, [100] = 0x11,
		[104] = 0x12, [108] = 0x13, [112] = 0x14, [116] = 0x15,
		[120] = 0x16,
	};
	cmd_usb_runtime_status_v1_t status = {
		.magic = SPF_RUNTIME_STATUS_MAGIC,
		.response_bytes = sizeof(cmd_usb_runtime_status_v1_t),
		.version = SPF_RUNTIME_STATUS_VERSION,
		.lifecycle_state = SPF_RUNTIME_STATE_STREAMING,
		.last_error_subsystem = SPF_ERROR_SUBSYSTEM_USB_SUBMIT,
		.last_errno = 5,
		.flags = SPF_RUNTIME_STATUS_FLAG_BOOT_ID_VALID |
			SPF_RUNTIME_STATUS_FLAG_PROCESS_NONCE_VALID |
			SPF_RUNTIME_STATUS_FLAG_RX_WORKER_ACTIVE,
		.current_stream_id = UINT64_C(0x0102030405060708),
		.last_completed_sequence = 9,
		.start_count = 10,
		.stop_count = 11,
		.completed_frame_count = 12,
		.dropped_frame_count = 13,
		.iio_refill_error_count = 14,
		.usb_submit_error_count = 15,
		.short_write_count = 16,
		.buffer_starvation_count = 17,
		.gain_read_failure_count = 18,
		.rssi_read_failure_count = 19,
		.control_error_count = 20,
		.stop_timeout_count = 21,
		.worker_heartbeat_age_ms = 22,
	};
	memset(status.boot_id, 0x11, sizeof(status.boot_id));
	memset(status.process_nonce, 0x22, sizeof(status.process_nonce));

	static const uint8_t identity_golden[64] = {
		0x53, 0x48, 0x46, 0x31, 0x40, 0x00, 0x01, 0x00,
		0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
		0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
		0x63, 0x63, 0x63, 0x63, 0x63, 0x63, 0x63, 0x63,
		0x63, 0x63, 0x63, 0x63, 0x63, 0x63, 0x63, 0x63,
		0x63, 0x63, 0x63, 0x63, 0x63, 0x63, 0x63, 0x63,
		0x63, 0x63, 0x63, 0x63, 0x63, 0x63, 0x63, 0x63,
		0x63, 0x63, 0x63, 0x63, 0x63, 0x63, 0x63, 0x63,
	};
	const cmd_usb_hardware_identity_v1_t identity = {
		.magic = SPF_HARDWARE_IDENTITY_MAGIC,
		.response_bytes = sizeof(cmd_usb_hardware_identity_v1_t),
		.version = SPF_HARDWARE_IDENTITY_VERSION,
		.flags = SPF_HARDWARE_IDENTITY_FLAG_BUILD_ID_VALID,
		.fpga_device_dna = 0,
		.gadget_build_id = {
			'c', 'c', 'c', 'c', 'c', 'c', 'c', 'c',
			'c', 'c', 'c', 'c', 'c', 'c', 'c', 'c',
			'c', 'c', 'c', 'c', 'c', 'c', 'c', 'c',
			'c', 'c', 'c', 'c', 'c', 'c', 'c', 'c',
			'c', 'c', 'c', 'c', 'c', 'c', 'c', 'c',
		},
	};

	static const uint8_t start_golden[32] = {
		0x53, 0x47, 0x53, 0x31, 0x01, 0x00, 0x20, 0x00,
		0x07, 0x00, 0x00, 0x00, 0x0f, 0x00, 0x00, 0x00,
		0x00, 0x00, 0x08, 0x00, 0x01, 0x00, 0x00, 0x00,
		0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
	};
	const cmd_usb_start_rx_v1_t start = {
		.magic = SPF_GADGET_START_V1_MAGIC,
		.protocol_version = SPF_GADGET_PROTOCOL_V1,
		.request_bytes = sizeof(cmd_usb_start_rx_v1_t),
		.requested_features =
			SPF_META_FEATURE_GAIN_ENDPOINT_SNAPSHOTS |
			SPF_META_FEATURE_HEADER_CRC32 |
			SPF_META_FEATURE_SAMPLE_SEQUENCE,
		.enabled_scan_mask = 0x0F,
		.samples_per_channel = 524288,
		.frame_count = 1,
	};
	static const uint8_t start_v2_golden[32] = {
		0x53, 0x47, 0x53, 0x32, 0x02, 0x00, 0x20, 0x00,
		0x37, 0x00, 0x00, 0x00, 0x0f, 0x00, 0x00, 0x00,
		0x00, 0x00, 0x08, 0x00, 0x01, 0x00, 0x00, 0x00,
		0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
	};
	const cmd_usb_start_rx_v1_t start_v2 = {
		.magic = SPF_GADGET_START_V2_MAGIC,
		.protocol_version = SPF_GADGET_PROTOCOL_V2,
		.request_bytes = sizeof(cmd_usb_start_rx_v1_t),
		.requested_features = SPF_META_REQUIRED_FEATURES_V2,
		.enabled_scan_mask = 0x0F,
		.samples_per_channel = 524288,
		.frame_count = 1,
	};

	return
		check_bytes(
			"capabilities",
			&capabilities,
			capabilities_golden,
			sizeof(capabilities)) ||
		check_bytes(
			"hardware identity",
			&identity,
			identity_golden,
			sizeof(identity)) ||
		check_bytes("runtime status", &status, status_golden, sizeof(status)) ||
		check_bytes("start", &start, start_golden, sizeof(start)) ||
		check_bytes("start v2", &start_v2, start_v2_golden, sizeof(start_v2));
}
