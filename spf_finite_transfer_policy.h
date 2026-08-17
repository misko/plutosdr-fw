#ifndef __SPF_FINITE_TRANSFER_POLICY_H__
#define __SPF_FINITE_TRANSFER_POLICY_H__

#include <stdbool.h>
#include <stddef.h>

/* Keep the disconnect policy host-testable and independent of FunctionFS.
 * Every short/error completion is fatal, including -ESHUTDOWN: on affected
 * hosts FunctionFS can leave UDC configured after the physical link vanished.
 */
static inline bool spf_usb_completion_requires_recovery(
	long completion_result,
	size_t expected_bytes)
{
	return completion_result < 0 ||
		(size_t)completion_result != expected_bytes;
}

#endif
