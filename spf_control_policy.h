#ifndef __SPF_CONTROL_POLICY_H__
#define __SPF_CONTROL_POLICY_H__

#include "sdr_usb_gadget_types.h"

typedef enum
{
	SPF_START_VALID = 0,
	SPF_START_INVALID_PROTOCOL,
	SPF_START_INVALID_FEATURES,
	SPF_START_INVALID_SCAN_MASK,
	SPF_START_INVALID_SAMPLE_COUNT,
	SPF_START_INVALID_FRAME_COUNT,
	SPF_START_INVALID_RESERVED,
	SPF_START_INVALID_OBSERVATION_INTERVAL,
	SPF_START_INVALID_SERIES_CAPACITY,
} spf_start_validation_t;

spf_start_validation_t spf_validate_start_rx_versioned(
	const cmd_usb_start_rx_v1_t *request);
const char *spf_start_validation_message(spf_start_validation_t result);

#endif
