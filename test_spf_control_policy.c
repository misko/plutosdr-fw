#include "spf_control_policy.h"
#include "spf_gain_metadata.h"

#include <assert.h>
#include <string.h>

static cmd_usb_start_rx_v1_t valid_request(void)
{
	cmd_usb_start_rx_v1_t request = {
		.magic = SPF_GADGET_START_V2_MAGIC,
		.protocol_version = SPF_GADGET_PROTOCOL_V2,
		.request_bytes = sizeof(cmd_usb_start_rx_v1_t),
		.requested_features = SPF_META_REQUIRED_FEATURES_V2,
		.enabled_scan_mask = UINT32_C(0x0F),
		.samples_per_channel = SPF_GADGET_MAX_SAMPLES_PER_CHANNEL,
		.frame_count = 1,
	};
	return request;
}

int main(void)
{
	cmd_usb_start_rx_v1_t request = valid_request();
	assert(spf_validate_start_rx_versioned(&request) == SPF_START_VALID);

	request.magic = 0;
	assert(spf_validate_start_rx_versioned(&request) ==
		SPF_START_INVALID_PROTOCOL);
	request = valid_request();
	request.requested_features ^= 1;
	assert(spf_validate_start_rx_versioned(&request) ==
		SPF_START_INVALID_FEATURES);
	request = valid_request();
	request.enabled_scan_mask = 3;
	assert(spf_validate_start_rx_versioned(&request) ==
		SPF_START_INVALID_SCAN_MASK);
	request = valid_request();
	request.samples_per_channel = 0;
	assert(spf_validate_start_rx_versioned(&request) ==
		SPF_START_INVALID_SAMPLE_COUNT);
	request = valid_request();
	request.samples_per_channel = SPF_GADGET_MAX_SAMPLES_PER_CHANNEL + 1;
	assert(spf_validate_start_rx_versioned(&request) ==
		SPF_START_INVALID_SAMPLE_COUNT);
	request = valid_request();
	request.frame_count = SPF_GADGET_MAX_FINITE_FRAMES + 1;
	assert(spf_validate_start_rx_versioned(&request) ==
		SPF_START_INVALID_FRAME_COUNT);
	request = valid_request();
	request.reserved1 = 1;
	assert(spf_validate_start_rx_versioned(&request) ==
		SPF_START_INVALID_RESERVED);
	assert(strcmp(
		spf_start_validation_message(SPF_START_INVALID_RESERVED),
		"reserved fields must be zero") == 0);
	return 0;
}
