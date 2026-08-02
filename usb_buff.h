#ifndef __USB_BUFF_H__
#define __USB_BUFF_H__

/* Standard libraries */
#include <stdint.h>

/* AsyncIO library */
#include "libaio.h"

/* Type definitions */
typedef struct
{
	/* AIO struct */
	struct iocb iocb;

	/* Buffer in use - command queued */
	bool in_use;
	bool sequence_valid;
	uint64_t sequence;

	/* Data buffer follows */
	uint8_t data[];

} usb_buf_t;

#endif
