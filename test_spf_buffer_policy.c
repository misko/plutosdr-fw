#include <assert.h>
#include <stdbool.h>
#include <stdint.h>

#include "spf_buffer_policy.h"

int main(void)
{
	assert(spf_usb_buffer_count(false, 0) == SPF_USB_BUFFER_LIMIT);
	assert(spf_usb_buffer_count(false, 1) == SPF_USB_BUFFER_LIMIT);
	assert(spf_usb_buffer_count(true, 0) == 0);
	assert(spf_usb_buffer_count(true, 1) == 1);
	assert(spf_usb_buffer_count(true, 3) == 3);
	assert(spf_usb_buffer_count(true, SPF_USB_BUFFER_LIMIT) ==
		SPF_USB_BUFFER_LIMIT);
	assert(spf_usb_buffer_count(true, SPF_USB_BUFFER_LIMIT + 1) ==
		SPF_USB_BUFFER_LIMIT);
	return 0;
}
