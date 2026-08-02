#include "spf_cleanup_plan.h"

#include <assert.h>
#include <stddef.h>

static void check_prefix(uint32_t acquired)
{
	uint32_t seen = 0;
	while (acquired != 0)
	{
		const spf_rx_resource_t next = spf_rx_cleanup_next(acquired);
		assert(next != SPF_RX_RESOURCE_NONE);
		assert((acquired & (uint32_t)next) != 0);
		assert((seen & (uint32_t)next) == 0);
		seen |= (uint32_t)next;
		acquired &= ~(uint32_t)next;
	}
}

int main(void)
{
	const spf_rx_resource_t acquisition_order[] = {
		SPF_RX_RESOURCE_EPOLL,
		SPF_RX_RESOURCE_IIO_CONTEXT,
		SPF_RX_RESOURCE_IIO_BUFFER,
		SPF_RX_RESOURCE_AIO_CONTEXT,
		SPF_RX_RESOURCE_AIO_EVENTFD,
		SPF_RX_RESOURCE_USB_BUFFERS,
		SPF_RX_RESOURCE_STATS_TIMER,
	};
	uint32_t acquired = 0;

	/* Every initialization failure is a prefix of the acquisition sequence. */
	check_prefix(acquired);
	for (size_t index = 0;
		index < sizeof(acquisition_order) / sizeof(acquisition_order[0]);
		++index)
	{
		acquired |= (uint32_t)acquisition_order[index];
		check_prefix(acquired);
	}

	assert(spf_rx_cleanup_next(acquired) == SPF_RX_RESOURCE_STATS_TIMER);
	acquired &= ~(uint32_t)SPF_RX_RESOURCE_STATS_TIMER;
	assert(spf_rx_cleanup_next(acquired) == SPF_RX_RESOURCE_AIO_CONTEXT);
	acquired &= ~(uint32_t)SPF_RX_RESOURCE_AIO_CONTEXT;
	assert(spf_rx_cleanup_next(acquired) == SPF_RX_RESOURCE_USB_BUFFERS);
	return 0;
}
