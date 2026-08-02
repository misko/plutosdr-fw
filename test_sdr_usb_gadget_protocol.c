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
		0x05, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
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
			SPF_GADGET_CAP_HARDWARE_IDENTITY,
	};

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
		check_bytes("start", &start, start_golden, sizeof(start)) ||
		check_bytes("start v2", &start_v2, start_v2_golden, sizeof(start_v2));
}
