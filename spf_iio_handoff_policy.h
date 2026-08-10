#ifndef SPF_IIO_HANDOFF_POLICY_H
#define SPF_IIO_HANDOFF_POLICY_H

#include <errno.h>
#include <stdbool.h>
#include <stdint.h>

/*
 * A remote iiod buffer teardown can briefly overlap the following direct-USB
 * START.  Wait for that ownership handoff, but never hide a persistent owner
 * or retry an unrelated initialization error.
 */
#define SPF_IIO_HANDOFF_RETRY_LIMIT UINT32_C(100)
#define SPF_IIO_HANDOFF_RETRY_DELAY_US UINT32_C(10000)

static inline bool spf_iio_handoff_should_retry(
	int error_number,
	uint32_t retries_already_used)
{
	return error_number == EBUSY &&
		retries_already_used < SPF_IIO_HANDOFF_RETRY_LIMIT;
}

#endif
