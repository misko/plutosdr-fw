#include "spf_finite_transfer_policy.h"

#include <assert.h>
#include <errno.h>

int main(void)
{
	assert(!spf_usb_completion_requires_recovery(4194400, 4194400));
	assert(spf_usb_completion_requires_recovery(4194399, 4194400));
	assert(spf_usb_completion_requires_recovery(-ESHUTDOWN, 4194400));
	assert(spf_usb_completion_requires_recovery(-EIO, 4194400));

	assert(!spf_finite_transfer_is_complete(false, 0, 0));
	assert(!spf_finite_transfer_is_complete(true, 1, 0));
	assert(!spf_finite_transfer_is_complete(true, 0, 1));
	assert(spf_finite_transfer_is_complete(true, 0, 0));
	return 0;
}
