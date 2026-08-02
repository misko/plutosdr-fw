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
#define SDR_USB_GADGET_COMMAND_GET_STATUS (0x15)
#define SDR_USB_GADGET_COMMAND_TARGET_RX (0x00)
#define SDR_USB_GADGET_COMMAND_TARGET_TX (0x01)

#define SPF_GADGET_CAPS_MAGIC UINT32_C(0x50434753) /* "SGCP" */
#define SPF_GADGET_START_V1_MAGIC UINT32_C(0x31534753) /* "SGS1" */
#define SPF_GADGET_START_V2_MAGIC UINT32_C(0x32534753) /* "SGS2" */
#define SPF_GADGET_PROTOCOL_V1 UINT16_C(1)
#define SPF_GADGET_PROTOCOL_V2 UINT16_C(2)
#define SPF_GADGET_MAX_FINITE_FRAMES UINT32_C(16)

/*
 * Largest finite dual-RX frame this firmware supports and advertises.
 *
 * This is an operational transport limit, not merely the largest sample
 * count whose byte-size arithmetic fits in uint32_t.  Hosts use this value to
 * size receive and stale-frame drain transfers.  Advertising UINT32_MAX / 8
 * caused two simultaneous receivers to each reserve an 8 MiB drain transfer,
 * exhausting the Raspberry Pi's default 16 MiB usbfs transfer-memory pool.
 * Rover production frames are 524288 samples/channel (4 MiB of CS16 IQ).
 */
#define SPF_GADGET_MAX_SAMPLES_PER_CHANNEL UINT32_C(524288)

#define SPF_GADGET_CAP_FINITE_RX (UINT32_C(1) << 0)
#define SPF_GADGET_CAP_DUMMY_GAINS (UINT32_C(1) << 1)
#define SPF_GADGET_CAP_HARDWARE_IDENTITY (UINT32_C(1) << 2)
#define SPF_GADGET_CAP_STATUS (UINT32_C(1) << 3)

#define SPF_HARDWARE_IDENTITY_MAGIC UINT32_C(0x31464853) /* "SHF1" */
#define SPF_HARDWARE_IDENTITY_VERSION UINT16_C(1)
#define SPF_HARDWARE_IDENTITY_FLAG_DNA_VALID (UINT32_C(1) << 0)
#define SPF_HARDWARE_IDENTITY_FLAG_BUILD_ID_VALID (UINT32_C(1) << 1)

#define SPF_RUNTIME_STATUS_MAGIC UINT32_C(0x31545353) /* "SST1" */
#define SPF_RUNTIME_STATUS_VERSION UINT16_C(1)
#define SPF_RUNTIME_STATUS_FLAG_BOOT_ID_VALID (UINT32_C(1) << 0)
#define SPF_RUNTIME_STATUS_FLAG_PROCESS_NONCE_VALID (UINT32_C(1) << 1)
#define SPF_RUNTIME_STATUS_FLAG_RX_WORKER_ACTIVE (UINT32_C(1) << 2)

typedef enum
{
	SPF_RUNTIME_STATE_IDLE = 0,
	SPF_RUNTIME_STATE_STARTING = 1,
	SPF_RUNTIME_STATE_STREAMING = 2,
	SPF_RUNTIME_STATE_COMPLETE = 3,
	SPF_RUNTIME_STATE_STOPPING = 4,
	SPF_RUNTIME_STATE_FAILED = 5,
} spf_runtime_state_t;

typedef enum
{
	SPF_ERROR_SUBSYSTEM_NONE = 0,
	SPF_ERROR_SUBSYSTEM_CONTROL = 1,
	SPF_ERROR_SUBSYSTEM_RX_INIT = 2,
	SPF_ERROR_SUBSYSTEM_IIO_REFILL = 3,
	SPF_ERROR_SUBSYSTEM_USB_SUBMIT = 4,
	SPF_ERROR_SUBSYSTEM_USB_COMPLETION = 5,
	SPF_ERROR_SUBSYSTEM_BUFFER_STARVATION = 6,
	SPF_ERROR_SUBSYSTEM_GAIN_READ = 7,
	SPF_ERROR_SUBSYSTEM_RSSI_READ = 8,
	SPF_ERROR_SUBSYSTEM_STOP_TIMEOUT = 9,
} spf_error_subsystem_t;

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

typedef struct
{
	uint32_t magic;
	uint16_t response_bytes;
	uint16_t version;
	uint16_t lifecycle_state;
	uint16_t last_error_subsystem;
	int32_t last_errno;
	uint32_t flags;
	uint32_t reserved0;
	uint8_t boot_id[16];
	uint8_t process_nonce[16];
	uint64_t current_stream_id;
	uint64_t last_completed_sequence;
	uint32_t start_count;
	uint32_t stop_count;
	uint32_t completed_frame_count;
	uint32_t dropped_frame_count;
	uint32_t iio_refill_error_count;
	uint32_t usb_submit_error_count;
	uint32_t short_write_count;
	uint32_t buffer_starvation_count;
	uint32_t gain_read_failure_count;
	uint32_t rssi_read_failure_count;
	uint32_t control_error_count;
	uint32_t stop_timeout_count;
	uint32_t worker_heartbeat_age_ms;
	uint32_t reserved1;
} cmd_usb_runtime_status_v1_t;
#pragma pack(pop)

_Static_assert(sizeof(cmd_usb_start_request_t) == 8,
	"legacy USB start request must remain 8 bytes");
_Static_assert(sizeof(cmd_usb_capabilities_v1_t) == 32,
	"SPF capability response must be 32 bytes");
_Static_assert(sizeof(cmd_usb_start_rx_v1_t) == 32,
	"SPF RX v1 start request must be 32 bytes");
_Static_assert(sizeof(cmd_usb_hardware_identity_v1_t) == 64,
	"SPF hardware identity response must be 64 bytes");
_Static_assert(sizeof(cmd_usb_runtime_status_v1_t) == 128,
	"SPF runtime status response must be 128 bytes");

#endif
