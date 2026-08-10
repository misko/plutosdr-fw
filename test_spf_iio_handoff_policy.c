#include <assert.h>
#include <errno.h>
#include <stdint.h>

#include "spf_iio_handoff_policy.h"

int main(void)
{
	assert(spf_iio_handoff_should_retry(EBUSY, 0));
	assert(spf_iio_handoff_should_retry(
		EBUSY,
		SPF_IIO_HANDOFF_RETRY_LIMIT - UINT32_C(1)));
	assert(!spf_iio_handoff_should_retry(
		EBUSY,
		SPF_IIO_HANDOFF_RETRY_LIMIT));
	assert(!spf_iio_handoff_should_retry(EAGAIN, 0));
	assert(!spf_iio_handoff_should_retry(EIO, 0));
	assert(SPF_IIO_HANDOFF_RETRY_LIMIT * SPF_IIO_HANDOFF_RETRY_DELAY_US ==
		UINT32_C(1000000));
	return 0;
}
