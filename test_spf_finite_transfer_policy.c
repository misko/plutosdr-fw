#include "spf_finite_transfer_policy.h"

#include <assert.h>
#include <errno.h>

int main(void)
{
	assert(!spf_usb_completion_requires_recovery(4194400, 4194400));
	assert(spf_usb_completion_requires_recovery(4194399, 4194400));
	assert(spf_usb_completion_requires_recovery(-ESHUTDOWN, 4194400));
	assert(spf_usb_completion_requires_recovery(-EIO, 4194400));

	return 0;
}
