#ifndef __SPF_CLEANUP_PLAN_H__
#define __SPF_CLEANUP_PLAN_H__

#include <stdint.h>

/*
 * RX resources are acquired incrementally but not all of them can be released
 * in simple reverse acquisition order.  In particular, Linux AIO must be
 * destroyed before its backing USB buffers are freed.  Keeping the ordering in
 * this small, host-testable policy prevents an error path from growing a
 * second, subtly different cleanup implementation.
 */
typedef enum
{
	SPF_RX_RESOURCE_NONE = 0,
	SPF_RX_RESOURCE_EPOLL = UINT32_C(1) << 0,
	SPF_RX_RESOURCE_IIO_CONTEXT = UINT32_C(1) << 1,
	SPF_RX_RESOURCE_IIO_BUFFER = UINT32_C(1) << 2,
	SPF_RX_RESOURCE_AIO_CONTEXT = UINT32_C(1) << 3,
	SPF_RX_RESOURCE_AIO_EVENTFD = UINT32_C(1) << 4,
	SPF_RX_RESOURCE_USB_BUFFERS = UINT32_C(1) << 5,
	SPF_RX_RESOURCE_STATS_TIMER = UINT32_C(1) << 6,
	SPF_RX_RESOURCE_FINITE_TRANSFER_TIMER = UINT32_C(1) << 7,
} spf_rx_resource_t;

static inline spf_rx_resource_t spf_rx_cleanup_next(uint32_t acquired)
{
	static const spf_rx_resource_t order[] = {
		SPF_RX_RESOURCE_FINITE_TRANSFER_TIMER,
		SPF_RX_RESOURCE_STATS_TIMER,
		SPF_RX_RESOURCE_AIO_CONTEXT,
		SPF_RX_RESOURCE_USB_BUFFERS,
		SPF_RX_RESOURCE_AIO_EVENTFD,
		SPF_RX_RESOURCE_IIO_BUFFER,
		SPF_RX_RESOURCE_IIO_CONTEXT,
		SPF_RX_RESOURCE_EPOLL,
	};

	for (unsigned int index = 0;
		index < sizeof(order) / sizeof(order[0]);
		++index)
	{
		if (acquired & (uint32_t)order[index])
			return order[index];
	}
	return SPF_RX_RESOURCE_NONE;
}

#endif
