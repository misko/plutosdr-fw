#include "spf_control_policy.h"

#include "spf_gain_metadata.h"

#include <stdbool.h>

spf_start_validation_t spf_validate_start_rx_versioned(
	const cmd_usb_start_rx_v1_t *request)
{
	const bool is_v1 =
		request->magic == SPF_GADGET_START_V1_MAGIC &&
		request->protocol_version == SPF_GADGET_PROTOCOL_V1;
	const bool is_v2 =
		request->magic == SPF_GADGET_START_V2_MAGIC &&
		request->protocol_version == SPF_GADGET_PROTOCOL_V2;
	if ((!is_v1 && !is_v2) || request->request_bytes != sizeof(*request))
		return SPF_START_INVALID_PROTOCOL;
	const uint32_t required_features = is_v1
		? SPF_META_REQUIRED_FEATURES_V1
		: SPF_META_REQUIRED_FEATURES_V2;
	if (request->requested_features != required_features)
		return SPF_START_INVALID_FEATURES;
	if (request->enabled_scan_mask != UINT32_C(0x0F))
		return SPF_START_INVALID_SCAN_MASK;
	if (request->samples_per_channel == 0 ||
		request->samples_per_channel > SPF_GADGET_MAX_SAMPLES_PER_CHANNEL)
		return SPF_START_INVALID_SAMPLE_COUNT;
	if (request->frame_count == 0 ||
		request->frame_count > SPF_GADGET_MAX_FINITE_FRAMES)
		return SPF_START_INVALID_FRAME_COUNT;
	if (request->reserved0 != 0 || request->reserved1 != 0)
		return SPF_START_INVALID_RESERVED;
	return SPF_START_VALID;
}

const char *spf_start_validation_message(spf_start_validation_t result)
{
	switch (result)
	{
		case SPF_START_VALID: return "valid";
		case SPF_START_INVALID_PROTOCOL: return "bad protocol identity or size";
		case SPF_START_INVALID_FEATURES: return "unsupported feature mask";
		case SPF_START_INVALID_SCAN_MASK: return "unsupported scan mask";
		case SPF_START_INVALID_SAMPLE_COUNT: return "invalid sample count";
		case SPF_START_INVALID_FRAME_COUNT: return "invalid frame count";
		case SPF_START_INVALID_RESERVED: return "reserved fields must be zero";
	}
	return "unknown validation result";
}
