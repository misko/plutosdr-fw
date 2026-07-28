#ifndef __SDR_USB_GADGET_TYPES_H__
#define __SDR_USB_GADGET_TYPES_H__

/* Standard libraries */
#include <stdint.h>

/* Definitions - commands */
#define SDR_USB_GADGET_COMMAND_START (0x10)
#define SDR_USB_GADGET_COMMAND_STOP (0x11)
#define SDR_USB_GADGET_COMMAND_GET_CAPABILITIES (0x12)
#define SDR_USB_GADGET_COMMAND_START_RX_V1 (0x13)
#define SDR_USB_GADGET_COMMAND_GET_HARDWARE_IDENTITY (0x14)
#define SDR_USB_GADGET_COMMAND_TARGET_RX (0x00)
#define SDR_USB_GADGET_COMMAND_TARGET_TX (0x01)

#define SPF_GADGET_CAPS_MAGIC UINT32_C(0x50434753) /* "SGCP" */
#define SPF_GADGET_START_V1_MAGIC UINT32_C(0x31534753) /* "SGS1" */
#define SPF_GADGET_START_V2_MAGIC UINT32_C(0x32534753) /* "SGS2" */
#define SPF_GADGET_PROTOCOL_V1 UINT16_C(1)
#define SPF_GADGET_PROTOCOL_V2 UINT16_C(2)
#define SPF_GADGET_MAX_FINITE_FRAMES UINT32_C(16)
#define SPF_GADGET_MAX_SAMPLES_PER_CHANNEL (UINT32_MAX / UINT32_C(8))

#define SPF_GADGET_CAP_FINITE_RX (UINT32_C(1) << 0)
#define SPF_GADGET_CAP_DUMMY_GAINS (UINT32_C(1) << 1)
#define SPF_GADGET_CAP_HARDWARE_IDENTITY (UINT32_C(1) << 2)

#define SPF_HARDWARE_IDENTITY_MAGIC UINT32_C(0x31464853) /* "SHF1" */
#define SPF_HARDWARE_IDENTITY_VERSION UINT16_C(1)
#define SPF_HARDWARE_IDENTITY_FLAG_DNA_VALID (UINT32_C(1) << 0)
#define SPF_HARDWARE_IDENTITY_FLAG_BUILD_ID_VALID (UINT32_C(1) << 1)

/* Type definitions */
#pragma pack(push,1)
typedef struct
{
	/* Bitmask of enabled channels */
	uint32_t enabled_channels;

	/*
	** Buffer size (in samples)
	** Note: This should include space for the 64-bit timestamp.
	** For example with RX0's I and Q channels enabled, each sample will be 2 * 16bit = 32bit
	** therefore a timestamp will occupy 64bit / 32bit = 2 samples. If a timestamp were to be provided
	** at the start of each buffer's worth of samples, an additional two samples would need to be added to
	** the buffer space.
	** Likewise if RX0 and RX1's I and Q channels were enabled, each sample will be 4 * 16bit = 64bit
	** as such only one sample would be required for the timestamp.
	*/
	uint32_t buffer_size;

} cmd_usb_start_request_t;

typedef struct
{
	uint32_t magic;
	uint16_t response_bytes;
	uint16_t protocol_min;
	uint16_t protocol_max;
	uint16_t reserved0;
	uint32_t supported_features;
	uint32_t max_samples_per_channel;
	uint32_t max_finite_frames;
	uint32_t capability_flags;
	uint32_t reserved1;
} cmd_usb_capabilities_v1_t;

typedef struct
{
	uint32_t magic;
	uint16_t protocol_version;
	uint16_t request_bytes;
	uint32_t requested_features;
	uint32_t enabled_scan_mask;
	uint32_t samples_per_channel;
	uint32_t frame_count;
	uint32_t reserved0;
	uint32_t reserved1;
} cmd_usb_start_rx_v1_t;

typedef struct
{
	uint32_t magic;
	uint16_t response_bytes;
	uint16_t version;
	uint32_t flags;
	uint32_t reserved0;
	uint64_t fpga_device_dna;
	char gadget_build_id[40];
} cmd_usb_hardware_identity_v1_t;
#pragma pack(pop)

_Static_assert(sizeof(cmd_usb_start_request_t) == 8,
	"legacy USB start request must remain 8 bytes");
_Static_assert(sizeof(cmd_usb_capabilities_v1_t) == 32,
	"SPF capability response must be 32 bytes");
_Static_assert(sizeof(cmd_usb_start_rx_v1_t) == 32,
	"SPF RX v1 start request must be 32 bytes");
_Static_assert(sizeof(cmd_usb_hardware_identity_v1_t) == 64,
	"SPF hardware identity response must be 64 bytes");

#endif
