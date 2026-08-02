/* Standard / system libraries */
#include <errno.h>
#include <fcntl.h>
#include <getopt.h>
#include <linux/usb/functionfs.h>
#include <pthread.h>
#include <signal.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/epoll.h>
#include <sys/eventfd.h>
#include <time.h>
#include <unistd.h>

/* libIIO */
#include <iio.h>

/* Local modules */
#include "epoll_loop.h"
#include "thread_read.h"
#include "thread_write.h"
#include "usb_descriptors.h"
#include "sdr_usb_gadget_types.h"
#include "spf_gain_metadata.h"
#include "spf_runtime_status.h"
#include "spf_thread_join.h"
#include "spf_control_policy.h"

/* Macros */
#define ARRAY_SIZE(x) (sizeof(x) / sizeof((x)[0]))
#define DEBUG_PRINT(...) if (debug) printf("Main: "__VA_ARGS__)
#define SPF_STOP_TIMEOUT_MS UINT32_C(3000)

/* Type definitions */
typedef struct
{
	/* Endpoint file descriptors */
	int ep[3];

	/* Eventfds to signal threads */
	int read_thread_event_fd;
	int write_thread_event_fd;

	/* Thread status */
	bool read_started;
	bool write_started;

	/* Thread arguments */
	THREAD_READ_Args_t read_args;
	THREAD_WRITE_Args_t write_args;

	/* Configuration enabled */
	bool config_enabled;

	/* Threads */
	pthread_t thread_read;
	pthread_t thread_write;

	/* Read-only status exposed through the control endpoint. */
	spf_runtime_status_t runtime_status;
	bool fatal_stop_failure;

} state_t;

/* Epoll event handler */
typedef int (*epoll_event_handler)(state_t *state);

/* Global variables */
bool debug;

/* Private function */
static int handle_ep0(state_t *state);
static bool start_thread(state_t *state, bool tx);
static bool stop_thread(state_t *state, bool tx);
static bool open_endpoints(state_t *state, const char* path);
static void close_endpoints(state_t *state);
static void signal_handler(int signum);
static void print_usage(const char *program_name, FILE *dest);
static const char* event_to_string(struct usb_functionfs_event *event);
static uint64_t next_stream_id(void);
static bool copy_build_id(char destination[40]);
static void note_control_error(state_t *state, const char *message);

/* Private variables */
static volatile sig_atomic_t keep_running = 1;

/* Public functions */
int main(int argc, char *argv[])
{
	state_t state;

	/* Reset state */
	memset(&state, 0x00, sizeof(state));
	if (!spf_runtime_status_init_auto(&state.runtime_status))
	{
		fprintf(stderr, "Failed to initialize runtime status\n");
		return 1;
	}

	/* Ensure stdout is line buffered */
	setlinebuf(stdout);

	/* Hello world */
	printf("Welcome!\n");
	printf("--------\n");

	/* Long options array, mapping options to their short equivalents */
	struct option long_options[] = {
		{"debug", no_argument, NULL, 'd'},
		{"version", no_argument, NULL, 'v'},
		{"help", no_argument, NULL, 'h'},
		{0, 0, 0, 0} // Terminate the options array
	};

	/* Basic argument parsing */
	int opt_c;
	bool err = false;
	while ((opt_c = getopt_long(argc, argv, "dhv", long_options, NULL)) != -1)
	{
			switch (opt_c)
			{
				case 'd':
				{
					debug = true;
					break;
				}
				case 'v':
				{
					printf("Version %s\n", PROGRAM_VERSION);
					return 0;
				}
				case 'h':
				{
					print_usage(argv[0], stdout);
					return 0;
				}
				case '?':
				{
					err = true;
					break;
				}
			}
	}
	if ((optind+1) > argc)
	{
		/* Missing FFS directory */
		fprintf(stderr, "Error: FFS_DIRECTORY is required\n");
		print_usage(argv[0], stderr);
		return 1;
	}
	else if (err)
	{
		/* Unrecognised argument */
		fprintf(stderr, "Error: Unrecognised argument\n");
		print_usage(argv[0], stderr);
		return 1;
	}

	/* Retrieve FFS directory */
	char *ffs_directory = argv[optind];

	/* Register signal handler */
	signal(SIGINT, signal_handler);
	signal(SIGTERM, signal_handler);

	/* Open endpoints */
	if (!open_endpoints(&state, ffs_directory))
		return 1;

	/* Prepare eventfds to notify threads to cancel */
	state.read_thread_event_fd = eventfd(0, 0);
	if (state.read_thread_event_fd < 0)
	{
		perror("Failed to open read eventfd");
		return 1;
	}
	else
	{
		DEBUG_PRINT("Opened read eventfd :-)\n");
	}
	state.write_thread_event_fd = eventfd(0, 0);
	if (state.write_thread_event_fd < 0)
	{
		perror("Failed to open write eventfd");
		return 1;
	}
	else
	{
		DEBUG_PRINT("Opened write eventfd :-)\n");
	}

	/* Prepare read args */
	state.read_args.quit_event_fd = state.read_thread_event_fd;
	state.read_args.output_fd = state.ep[1];
	state.read_args.runtime_status = &state.runtime_status;

	/* Prepare write args */
	state.write_args.quit_event_fd = state.write_thread_event_fd;
	state.write_args.input_fd = state.ep[2];

	/* Create epoll instance */
	int epoll_fd = epoll_create1(0);
	if (epoll_fd < 0)
	{
		perror("Failed to create epoll instance");
		return 1;
	}
	else
	{
		DEBUG_PRINT("Opened epoll :-)\n");
	}

	struct epoll_event epoll_event;

	/* Register ep0 with epoll */
	epoll_event.events = EPOLLIN;
	epoll_event.data.ptr = handle_ep0;
	if (epoll_ctl(epoll_fd, EPOLL_CTL_ADD, state.ep[0], &epoll_event) < 0)
	{
		/* Failed to register ep0 with epoll */
		perror("Failed to register ep0 with epoll");
		return 1;
	}
	else
	{
		DEBUG_PRINT("Registered ep0 with epoll :-)\n");
	}

	/* Here we go */
	printf("Ready :-)\n");
	fflush(stdout);

	/* Enter main loop */
	DEBUG_PRINT("Enter main loop..\n");
	while (keep_running)
	{
		/* Run epoll until it or one of its handlers fails */
		if (EPOLL_LOOP_Run(epoll_fd, 30000, &state) < 0)
		{
			/* Handler failed...bail */
			break;
		}
	}
	DEBUG_PRINT("Exit main loop :-(\n");

	/* Stop threads unless a timed-out worker still owns their resources. */
	if (!state.fatal_stop_failure)
	{
		stop_thread(&state, false);
		stop_thread(&state, true);
	}
	if (state.fatal_stop_failure)
	{
		fprintf(stderr,
			"Fatal worker-stop failure; exiting for supervised recovery\n");
		fflush(NULL);
		_exit(2);
	}

	/* Close files */
	close(epoll_fd);
	close(state.read_thread_event_fd);
	close(state.write_thread_event_fd);
	close_endpoints(&state);
	spf_runtime_status_destroy(&state.runtime_status);

	/* Goodbye */
	printf("Bye!\n");

	return 0;
}

/* Private functions */
static int handle_ep0(state_t *state)
{
	struct usb_functionfs_event event;
	int ret;

	/* Read event from ep0 */
	ret = read(state->ep[0], &event, sizeof(event));
	if (sizeof(event) != ret)
	{
		perror("Failed to read event from ep0");
		return -1;
	}

	/* Print event summary */
	DEBUG_PRINT("Handle ep0 event: %s\n", event_to_string(&event));

	switch (event.type)
	{
		case FUNCTIONFS_SETUP:
		{
			DEBUG_PRINT("Received setup control transfer: bRequestType = %d, bRequest = %d, wValue = %d, wIndex = %d, wLength = %d\n",
						(int)event.u.setup.bRequestType,
						(int)event.u.setup.bRequest,
						(int)event.u.setup.wValue,
						(int)event.u.setup.wIndex,
						(int)event.u.setup.wLength
					   );

			if (event.u.setup.bRequestType & USB_DIR_IN)
			{
				if (event.u.setup.bRequest == SDR_USB_GADGET_COMMAND_GET_CAPABILITIES)
				{
					const cmd_usb_capabilities_v1_t capabilities = {
						.magic = SPF_GADGET_CAPS_MAGIC,
						.response_bytes = sizeof(cmd_usb_capabilities_v1_t),
						.protocol_min = SPF_GADGET_PROTOCOL_V1,
						.protocol_max = SPF_GADGET_PROTOCOL_V2,
						.reserved0 = 0,
						.supported_features =
							SPF_META_FEATURE_GAIN_ENDPOINT_SNAPSHOTS |
							SPF_META_FEATURE_HEADER_CRC32 |
							SPF_META_FEATURE_SAMPLE_SEQUENCE |
							SPF_META_FEATURE_GAIN_DB_ENDPOINTS |
							SPF_META_FEATURE_RSSI_ENDPOINT_SNAPSHOTS,
						.max_samples_per_channel =
							SPF_GADGET_MAX_SAMPLES_PER_CHANNEL,
						.max_finite_frames = SPF_GADGET_MAX_FINITE_FRAMES,
						.capability_flags =
							SPF_GADGET_CAP_FINITE_RX |
							SPF_GADGET_CAP_HARDWARE_IDENTITY |
							SPF_GADGET_CAP_STATUS,
						.reserved1 = 0,
					};
					size_t response_bytes = sizeof(capabilities);
					if (event.u.setup.wLength < response_bytes)
						response_bytes = event.u.setup.wLength;
					if (write(state->ep[0], &capabilities, response_bytes) < 0)
					{
						perror("Failed to write capabilities to host");
						return -1;
					}
				}
				else if (event.u.setup.bRequest ==
					SDR_USB_GADGET_COMMAND_GET_HARDWARE_IDENTITY)
				{
					cmd_usb_hardware_identity_v1_t identity = {
						.magic = SPF_HARDWARE_IDENTITY_MAGIC,
						.response_bytes =
							sizeof(cmd_usb_hardware_identity_v1_t),
						.version = SPF_HARDWARE_IDENTITY_VERSION,
						.flags = 0,
						.reserved0 = 0,
						.fpga_device_dna = 0,
						.gadget_build_id = {0},
					};
					if (copy_build_id(identity.gadget_build_id))
					{
						identity.flags |=
							SPF_HARDWARE_IDENTITY_FLAG_BUILD_ID_VALID;
					}
					size_t response_bytes = sizeof(identity);
					if (event.u.setup.wLength < response_bytes)
						response_bytes = event.u.setup.wLength;
					if (write(state->ep[0], &identity, response_bytes) < 0)
					{
						perror("Failed to write hardware identity to host");
						return -1;
					}
				}
				else if (event.u.setup.bRequest ==
					SDR_USB_GADGET_COMMAND_GET_STATUS)
				{
					cmd_usb_runtime_status_v1_t status;
					spf_runtime_status_snapshot(
						&state->runtime_status,
						&status);
					size_t response_bytes = sizeof(status);
					if (event.u.setup.wLength < response_bytes)
						response_bytes = event.u.setup.wLength;
					if (write(state->ep[0], &status, response_bytes) < 0)
					{
						perror("Failed to write runtime status to host");
						return -1;
					}
				}
				else if (write(state->ep[0], NULL, 0) < 0)
				{
					perror("Failed to write empty packet to host");
					return -1;
				}
			}
			else
			{
				uint8_t control_in_data[64];
				const cmd_usb_start_request_t *cmd_start_req = (const cmd_usb_start_request_t*)control_in_data;
				const cmd_usb_start_rx_v1_t *cmd_start_rx_v1 = (const cmd_usb_start_rx_v1_t*)control_in_data;

				/* Read request */
				ssize_t read_count = read(state->ep[0], control_in_data, sizeof(control_in_data));
				if (read_count < 0)
				{
					perror("Failed to read packet from host");
					return -1;
				}

				/* Act on request */
				switch (event.u.setup.bRequest)
				{
					case SDR_USB_GADGET_COMMAND_START:
					{
						/* Check request size */
						if (read_count != sizeof(*cmd_start_req))
						{
							note_control_error(
								state,
								"legacy START has incorrect data size");
							break;
						}
						if (event.u.setup.wValue !=
							SDR_USB_GADGET_COMMAND_TARGET_RX &&
							event.u.setup.wValue !=
							SDR_USB_GADGET_COMMAND_TARGET_TX)
						{
							note_control_error(
								state,
								"legacy START has invalid target");
							break;
						}

						/* Decide on TX vs RX thread */
						bool tx = (SDR_USB_GADGET_COMMAND_TARGET_TX == event.u.setup.wValue);

						/* Ensure thread stopped */
						if (!stop_thread(state, tx))
							return -1;

						/* Act on direction */
						if (tx)
						{
							/* TX thread, store args */
							state->write_args.iio_channels = cmd_start_req->enabled_channels;
							state->write_args.iio_buffer_size = cmd_start_req->buffer_size;
						}
						else
						{
							/* RX thread, store args */
							state->read_args.iio_channels = cmd_start_req->enabled_channels;
							state->read_args.iio_buffer_size = cmd_start_req->buffer_size;
							state->read_args.protocol_version = 0;
							state->read_args.metadata_features = 0;
							state->read_args.frame_count = 0;
							state->read_args.stream_id = 0;
						}

						/* Start thread */
						if (!start_thread(state, tx))
							return -1;
						break;
					}
					case SDR_USB_GADGET_COMMAND_START_RX_V1:
					{
						if (event.u.setup.wValue != SDR_USB_GADGET_COMMAND_TARGET_RX)
						{
							note_control_error(
								state,
								"versioned START is RX-only");
							break;
						}
						if (read_count != sizeof(*cmd_start_rx_v1))
						{
							note_control_error(
								state,
								"versioned START has incorrect data size");
							break;
						}
					spf_start_validation_t validation =
						spf_validate_start_rx_versioned(cmd_start_rx_v1);
					if (validation != SPF_START_VALID)
					{
						fprintf(stderr,
							"Rejected versioned RX START: %s\n",
							spf_start_validation_message(validation));
						spf_runtime_status_increment(
							&state->runtime_status,
							SPF_STATUS_COUNTER_CONTROL_ERROR);
						spf_runtime_status_note_error(
							&state->runtime_status,
							SPF_ERROR_SUBSYSTEM_CONTROL,
							EINVAL);
						break;
					}

						if (!stop_thread(state, false))
							return -1;
						state->read_args.iio_channels = cmd_start_rx_v1->enabled_scan_mask;
						state->read_args.iio_buffer_size = cmd_start_rx_v1->samples_per_channel;
						state->read_args.protocol_version = cmd_start_rx_v1->protocol_version;
						state->read_args.metadata_features = cmd_start_rx_v1->requested_features;
						state->read_args.frame_count = cmd_start_rx_v1->frame_count;
						state->read_args.stream_id = next_stream_id();
						spf_runtime_status_set_stream(
							&state->runtime_status,
							state->read_args.stream_id);
						spf_runtime_status_increment(
							&state->runtime_status,
							SPF_STATUS_COUNTER_START);
						spf_runtime_status_set_state(
							&state->runtime_status,
							SPF_RUNTIME_STATE_STARTING,
							false);
						if (!start_thread(state, false))
						{
							spf_runtime_status_record_error(
								&state->runtime_status,
								SPF_ERROR_SUBSYSTEM_RX_INIT,
								errno);
							return -1;
						}
						break;
					}
					case SDR_USB_GADGET_COMMAND_STOP:
					{
						/* Decide on TX vs RX thread */
						bool tx = (0 != event.u.setup.wValue);
						if (event.u.setup.wValue !=
							SDR_USB_GADGET_COMMAND_TARGET_RX &&
							event.u.setup.wValue !=
							SDR_USB_GADGET_COMMAND_TARGET_TX)
						{
							note_control_error(
								state,
								"STOP has invalid target");
							break;
						}

						/* Stop thread */
						if (!tx)
						{
							spf_runtime_status_increment(
								&state->runtime_status,
								SPF_STATUS_COUNTER_STOP);
							spf_runtime_status_set_state(
								&state->runtime_status,
								SPF_RUNTIME_STATE_STOPPING,
								state->read_started);
						}
						if (!stop_thread(state, tx))
							return -1;
						if (!tx)
							spf_runtime_status_set_state(
								&state->runtime_status,
								SPF_RUNTIME_STATE_IDLE,
								false);
						break;
					}
					default:
					{
						note_control_error(
							state,
							"unknown vendor control request");
						break;
					}
				}
			}
			break;
		}
		case FUNCTIONFS_DISABLE:
		{
			if (state->config_enabled)
			{
				/* Stop threads */
				if (!(	  stop_thread(state, false)
					   && stop_thread(state, true)
					 )
				   )
				{
					/* Failed to stop a thread */
					return -1;
				}
			}

			/* Flag disabled */
			state->config_enabled = false;
			break;
		}
		case FUNCTIONFS_ENABLE:
		{
			/* Flag enabled */
			state->config_enabled = true;
			break;
		}
		default:
		{
			/* Ignore unknown requests */
			break;
		}
	}

	return 0;
}

static bool copy_build_id(char destination[40])
{
	const char *source = PROGRAM_VERSION;
	if (strlen(source) != 40)
		return false;
	for (size_t index = 0; index < 40; ++index)
	{
		const char value = source[index];
		if (!((value >= '0' && value <= '9') ||
			(value >= 'a' && value <= 'f')))
		{
			memset(destination, 0, 40);
			return false;
		}
		destination[index] = value;
	}
	return true;
}

static void note_control_error(state_t *state, const char *message)
{
	fprintf(stderr, "Rejected control request: %s\n", message);
	spf_runtime_status_increment(
		&state->runtime_status,
		SPF_STATUS_COUNTER_CONTROL_ERROR);
	spf_runtime_status_note_error(
		&state->runtime_status,
		SPF_ERROR_SUBSYSTEM_CONTROL,
		EINVAL);
}

static uint64_t next_stream_id(void)
{
	static uint64_t start_counter;
	struct timespec now = {0, 0};
	clock_gettime(CLOCK_MONOTONIC, &now);
	uint64_t id =
		((uint64_t)now.tv_sec * UINT64_C(1000000000)) +
		(uint64_t)now.tv_nsec +
		++start_counter;
	return id == 0 ? 1 : id;
}

static bool start_thread(state_t *state, bool tx)
{
	/* Mask all signals (such that threads will by default not handle them) */
	sigset_t new_mask, old_mask;
	sigfillset(&new_mask);
	if (sigprocmask(SIG_SETMASK, &new_mask, &old_mask) < 0)
	{
		perror("Failed to mask signals");
		return false;
	}

	bool started = true;
	/* Create appropriate thread */
	if (tx && !state->write_started)
	{
		/* Start thread */
		state->write_started = (0 == pthread_create(&state->thread_write, NULL, &THREAD_WRITE_Entrypoint, &state->write_args));
		if (!state->write_started)
		{
			perror("Failed to start write thread");
			started = false;
		}
	}
	else if (!tx && !state->read_started)
	{
		/* Start thread */
		state->read_started = (0 == pthread_create(&state->thread_read, NULL, &THREAD_READ_Entrypoint, &state->read_args));
		if (!state->read_started)
		{
			perror("Failed to start read thread");
			started = false;
		}
	}

	/* Return signal mask to old value, such that all signals will be handled by main thread */
	if (sigprocmask(SIG_SETMASK, &old_mask, NULL) < 0)
	{
		perror("Failed to unmask signals");
		return false;
	}

	return started;
}

static bool stop_thread(state_t *state, bool tx)
{
	if (tx && state->write_started)
	{
		/* Write eventfd to signal thread to stop */
		uint64_t eventfd_val = 0x1;
		if (write(state->write_thread_event_fd, &eventfd_val, sizeof(eventfd_val)) < 0)
		{
			perror("Failed to write to write thread eventfd");
			return false;
		}

		/* Join with a bound so ep0 cannot hang forever. */
		int join_error = 0;
		spf_thread_join_result_t join_result = spf_thread_join_bounded(
			state->thread_write,
			SPF_STOP_TIMEOUT_MS,
			&join_error);
		if (join_result != SPF_THREAD_JOIN_OK)
		{
			errno = join_error;
			perror("Timed write-worker join failed");
			state->fatal_stop_failure = true;
			return false;
		}

		/* Read eventfd now thread has stopped to reset it */
		if (read(state->write_thread_event_fd, &eventfd_val, sizeof(eventfd_val)) < 0)
		{
			perror("Failed to read from write thread eventfd");
			return false;
		}

		/* Clear running flag */
		state->write_started = false;
	}
	else if (!tx && state->read_started)
	{
		/* Write eventfd to signal thread to stop */
		uint64_t eventfd_val = 0x1;
		if (write(state->read_thread_event_fd, &eventfd_val, sizeof(eventfd_val)) < 0)
		{
			perror("Failed to write to read thread eventfd");
			return false;
		}

		/* Join with a bound so ep0 cannot hang forever. */
		int join_error = 0;
		spf_thread_join_result_t join_result = spf_thread_join_bounded(
			state->thread_read,
			SPF_STOP_TIMEOUT_MS,
			&join_error);
		if (join_result != SPF_THREAD_JOIN_OK)
		{
			if (join_result == SPF_THREAD_JOIN_TIMEOUT)
				spf_runtime_status_increment(
					&state->runtime_status,
					SPF_STATUS_COUNTER_STOP_TIMEOUT);
			spf_runtime_status_record_error(
				&state->runtime_status,
				SPF_ERROR_SUBSYSTEM_STOP_TIMEOUT,
				join_error);
			errno = join_error;
			perror("Timed read-worker join failed");
			state->fatal_stop_failure = true;
			return false;
		}

		/* Read eventfd now thread has stopped to reset it */
		if (read(state->read_thread_event_fd, &eventfd_val, sizeof(eventfd_val)) < 0)
		{
			perror("Failed to read from read thread eventfd");
			return false;
		}

		/* Clear running flag */
		state->read_started = false;
	}

	return true;
}

static bool open_endpoints(state_t *state, const char* path)
{
	/* Prepare buffer for endpoint paths */
	char *ep_path = malloc(strlen(path) + 4 /* "/ep#" */ + 1 /* '\0' */);
	if (!ep_path)
	{
		perror("Failed to allocate endpoint path buffer");
		return false;
	}

	/* Open and prepare EP0 */
	sprintf(ep_path, "%s/ep0", path);
	DEBUG_PRINT("Opening: %s...\n", ep_path);
	state->ep[0] = open(ep_path, O_RDWR);
	if (state->ep[0] < 0)
	{
		perror("Failed to open ep0");
		return false;
	}
	else
	{
		DEBUG_PRINT("Opened ep0 :-)\n");
	}

	/* Provide descriptors and strings to kernel, writing them to ep0 */
	if (!USB_DESCRIPTORS_WriteToEP0(state->ep[0]))
		return false;

	/* Open bulk in/out endpoints */
	sprintf(ep_path, "%s/ep1", path);
	DEBUG_PRINT("Opening: %s...\n", ep_path);
	state->ep[1] = open(ep_path, O_WRONLY);
	if (state->ep[1] < 0)
	{
		perror("Failed to open ep1");
		return false;
	}
	else
	{
		DEBUG_PRINT("Opened ep1 :-)\n");
	}

	sprintf(ep_path, "%s/ep2", path);
	DEBUG_PRINT("Opening: %s...\n", ep_path);
	state->ep[2] = open(ep_path, O_RDONLY);
	if (state->ep[2] < 0)
	{
		perror("Failed to open ep2");
		return false;
	}
	else
	{
		DEBUG_PRINT("Opened ep2 :-)\n");
	}

	/* Free endpoint path buffer */
	free(ep_path);
	ep_path = NULL;

	return true;
}

static void close_endpoints(state_t *state)
{
	/* Close endpoints */
	for (unsigned int i = 0; i < ARRAY_SIZE(state->ep); i++)
	{
		close(state->ep[i]);
	}
}

static void signal_handler(int signum)
{
	(void)signum;

	/* Clear running flag */
	keep_running = 0;
}

static void print_usage(const char *program_name, FILE *dest)
{
	fprintf(dest, "Usage: %s [OPTIONS] FFS_DIRECTORY\n", program_name);
	fprintf(dest, "OPTIONS:\n");
	fprintf(dest, "  -h, --help\tDisplay this help message\n");
	fprintf(dest, "  -d, --debug\tEnable debug output\n");
	fprintf(dest, "  -v, --version\tDisplay the version of the program\n");
}

static const char* event_to_string(struct usb_functionfs_event *event)
{
	/* Event type names */
	static const char *const names[] =
	{
		[FUNCTIONFS_BIND] = "BIND",
		[FUNCTIONFS_UNBIND] = "UNBIND",
		[FUNCTIONFS_ENABLE] = "ENABLE",
		[FUNCTIONFS_DISABLE] = "DISABLE",
		[FUNCTIONFS_SETUP] = "SETUP",
		[FUNCTIONFS_SUSPEND] = "SUSPEND",
		[FUNCTIONFS_RESUME] = "RESUME",
	};

	/* Lookup event type name */
	switch (event->type)
	{
		case FUNCTIONFS_BIND:
		case FUNCTIONFS_UNBIND:
		case FUNCTIONFS_ENABLE:
		case FUNCTIONFS_DISABLE:
		case FUNCTIONFS_SETUP:
		case FUNCTIONFS_SUSPEND:
		case FUNCTIONFS_RESUME:
			return names[event->type];
		default:
			return "UNKNOWN";
	}
}
