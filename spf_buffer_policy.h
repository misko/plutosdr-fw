#ifndef __SPF_BUFFER_POLICY_H__
#define __SPF_BUFFER_POLICY_H__

#include <stdbool.h>
#include <stdint.h>

#define SPF_USB_BUFFER_LIMIT UINT32_C(16)
#define SPF_IIO_KERNEL_BUFFER_COUNT 8U

/*
 * Legacy unbounded streaming retains the historical queue depth. A finite
 * versioned request cannot consume more USB buffers than frames it will ever
 * submit. Returning zero for an invalid zero-frame request keeps the policy
 * fail-closed; request validation rejects it before io_setup().
 */
static inline uint32_t spf_usb_buffer_count(
	bool finite_request,
	uint32_t frame_count)
{
	if (!finite_request)
		return SPF_USB_BUFFER_LIMIT;
	if (frame_count < SPF_USB_BUFFER_LIMIT)
		return frame_count;
	return SPF_USB_BUFFER_LIMIT;
}

#endif
