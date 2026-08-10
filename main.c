/* Standard / system libraries */
#include <arpa/inet.h>
#include <errno.h>
#include <getopt.h>
#include <inttypes.h>
#include <netinet/in.h>
#include <pthread.h>
#include <signal.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/epoll.h>
#include <sys/eventfd.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <time.h>
#include <unistd.h>

/* libIIO */
#include <iio.h>

/* Local modules */
#include "sdr_ip_gadget_types.h"
#include "epoll_loop.h"
#include "thread_read.h"
#include "thread_read_v3.h"
#include "thread_write.h"
#include "spf_ip_protocol.h"
#include "spf_ip_tx_policy.h"
#include "spf_ip_control_replay.h"
#include "spf_ip_rx_lifecycle.h"
#include <spf/spf_time_anchor.h>

/* Macros */
#define ARRAY_SIZE(x) (sizeof(x) / sizeof((x)[0]))
#define DEBUG_PRINT(...) if (debug) printf("Main: "__VA_ARGS__)

/* Definitions - UDP port numbers */
#define DIRECT_IP_PORT_CONTROL (30432) // IIOD + 1
#define DIRECT_IP_PORT_DATA (30433) // IIOD + 2
#define SPF_IP_SOCKET_BUFFER_BYTES (8 * 1024 * 1024)

/* Type definitions */
typedef struct
{
	/* Socket file descriptors */
	int sock_control;
	int sock_data;

	/* Eventfds to signal threads */
	int read_thread_event_fd;
	int read_v3_startup_event_fd;
	int read_v3_run_event_fd;
	int read_v3_quit_event_fd;
	int read_v3_done_event_fd;
	int write_thread_event_fd;

	/* Thread status */
	bool read_started;
	bool read_v3_started;
	bool write_started;

	/* Thread arguments */
	THREAD_READ_Args_t read_args;
	THREAD_READ_V3_Args_t read_v3_args;
	THREAD_WRITE_Args_t write_args;

	/* Threads */
	pthread_t thread_read;
	pthread_t thread_read_v3;
	pthread_t thread_write;

	uint64_t next_stream_id;
	uint64_t active_v3_stream_id;
	spf_ip_rx_lifecycle_t rx_lifecycle;
	spf_ip_control_replay_t control_replay;
	int pending_start_slot;
	int pending_stop_slot;
	struct sockaddr_in pending_start_peer;
	struct sockaddr_in pending_stop_peer;
	bool read_v3_quit_signaled;
	uint64_t v3_start_count;
	uint64_t v3_stop_count;
	uint64_t v3_worker_done_count;

	spf_time_anchor_reader_t time_anchor_reader;
	bool time_anchor_cache_valid;
	struct sockaddr_in time_anchor_cache_peer;
	spf_time_anchor_query_v1_t time_anchor_cache_query;
	spf_time_anchor_v1_t time_anchor_cache_reply;

} state_t;

/* Epoll event handler */
typedef int (*epoll_event_handler)(state_t *state);

/* Global variables */
bool debug;

/* Private function */
static int handle_control(state_t *state);
static int handle_v3_startup_event(state_t *state);
static int handle_v3_done_event(state_t *state);
static int handle_v3_control(state_t *state,
	const spf_ip_control_v1_t *request,
	const struct sockaddr_in *peer);
static bool send_v3_control(state_t *state,
	const spf_ip_control_v1_t *response,
	const struct sockaddr_in *peer);
static bool same_control_peer(
	const struct sockaddr_in *left,
	const struct sockaddr_in *right);
static bool start_thread(state_t *state, bool tx);
static bool stop_thread(state_t *state, bool tx);
static bool launch_v3_thread(state_t *state);
static bool request_v3_stop(state_t *state);
static bool stop_v3_thread(state_t *state);
static bool prepare_and_send_control(state_t *state,
	int slot,
	const spf_ip_control_v1_t *response,
	const struct sockaddr_in *peer);
static void on_control_response_sent(state_t *state, int slot);
static bool cache_immediate_control(state_t *state,
	const spf_ip_control_v1_t *request,
	const spf_ip_control_v1_t *response,
	const struct sockaddr_in *peer);
static void reset_v3_eventfds(state_t *state);
static void signal_handler(int signum);
static void print_usage(const char *program_name, FILE *dest);
static const char* cmd_name(uint32_t cmd);

/* Private variables */
static volatile sig_atomic_t keep_running = 1;

/* Public functions */
int main(int argc, char *argv[])
{
	state_t state;
	struct sockaddr_in addr;

	/* Reset state */
	memset(&state, 0x00, sizeof(state));
	state.pending_start_slot = -1;
	state.pending_stop_slot = -1;
	spf_ip_rx_lifecycle_init(&state.rx_lifecycle);
	spf_ip_control_replay_init(&state.control_replay);
	state.next_stream_id = ((uint64_t)time(NULL) << 32) |
		(uint32_t)getpid();
	if (state.next_stream_id == 0)
		state.next_stream_id = 1;
	if (!spf_time_anchor_reader_init(&state.time_anchor_reader))
	{
		fprintf(stderr, "Required FPGA time-anchor counter is unavailable\n");
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
	if (err)
	{
		/* Unrecognised argument */
		fprintf(stderr, "Error: Unrecognised argument\n");
		print_usage(argv[0], stderr);
		return 1;
	}

	/* Register signal handler */
	signal(SIGINT, signal_handler);
	signal(SIGTERM, signal_handler);

	/* Open sockets */
	state.sock_control = socket(AF_INET, SOCK_DGRAM, 0);
	if (state.sock_control < 0)
	{
		perror("Failed to open control socket");
		return false;
	}
	else
	{
		DEBUG_PRINT("Opened control socket :-)\n");
	}
	state.sock_data = socket(AF_INET, SOCK_DGRAM, 0);
	if (state.sock_data < 0)
	{
		perror("Failed to open data socket");
		return false;
	}
	else
	{
		DEBUG_PRINT("Opened data socket :-)\n");
	}

	/* Place sockets in non-blocking mode */
	int nonblocking = 1;
	if (ioctl(state.sock_control, FIONBIO, &nonblocking) != 0)
	{
		perror("Failed to set control socket mode to non-blocking");
		return 1;
	}
	if (ioctl(state.sock_data, FIONBIO, &nonblocking) != 0)
	{
		perror("Failed to set data socket mode to non-blocking");
		return 1;
	}

    // Get the current send buffer size
    int send_size;
	socklen_t size_len = sizeof(send_size);
    if (getsockopt(state.sock_data, SOL_SOCKET, SO_SNDBUF, &send_size, &size_len) == -1)
	{
        perror("getsockopt for send buffer size");
        return 1;
    }

    // Get the current receive buffer size
    int recv_size;
    size_len = sizeof(recv_size);
    if (getsockopt(state.sock_data, SOL_SOCKET, SO_RCVBUF, &recv_size, &size_len) == -1)
	{
        perror("getsockopt for receive buffer size");
        return 1;
    }

	// Report current sizes
    DEBUG_PRINT("Current socket send = %d receive = %d\n", send_size, recv_size);

	// Set the send buffer size
	send_size = SPF_IP_SOCKET_BUFFER_BYTES;
    if (setsockopt(state.sock_data, SOL_SOCKET, SO_SNDBUF, &send_size, sizeof(send_size)) == -1)
	{
        perror("setsockopt for send buffer size");
        return 1;
    }

	// Set the receive buffer size
	recv_size = SPF_IP_SOCKET_BUFFER_BYTES;
    if (setsockopt(state.sock_data, SOL_SOCKET, SO_RCVBUF, &recv_size, sizeof(send_size)) == -1)
	{
        perror("setsockopt for receive buffer size");
        return 1;
    }

    // Get the updated send buffer size
	size_len = sizeof(send_size);
    if (getsockopt(state.sock_data, SOL_SOCKET, SO_SNDBUF, &send_size, &size_len) == -1)
	{
        perror("getsockopt for send buffer size");
        return 1;
    }

    // Get the updated receive buffer size
    size_len = sizeof(recv_size);
    if (getsockopt(state.sock_data, SOL_SOCKET, SO_RCVBUF, &recv_size, &size_len) == -1)
	{
        perror("getsockopt for receive buffer size");
        return 1;
    }

	// Report updated sizes
    DEBUG_PRINT("Updated socket send = %d receive = %d\n", send_size, recv_size);

	/* Bind sockets */
	memset(&addr, 0x00, sizeof(addr));
	addr.sin_family = AF_INET;
	addr.sin_addr.s_addr = INADDR_ANY;
	addr.sin_port = htons(DIRECT_IP_PORT_CONTROL);
	if (bind(state.sock_control, (const struct sockaddr *)&addr, sizeof(addr)))
	{
		perror("Failed to bind control socket");
		return 1;
	}
	else
	{
		DEBUG_PRINT("Bound control socket :-)\n");
	}
	addr.sin_port = htons(DIRECT_IP_PORT_DATA);
	if (bind(state.sock_data, (const struct sockaddr *)&addr, sizeof(addr)))
	{
		perror("Failed to bind data socket");
		return 1;
	}
	else
	{
		DEBUG_PRINT("Bound data socket :-)\n");
	}

	/* Prepare eventfds to notify threads to cancel */
	state.read_thread_event_fd = eventfd(0, 0);
	if (state.read_thread_event_fd < 0)
	{
		perror("Failed to open read eventfd");
		return 1;
	}
	state.read_v3_startup_event_fd = eventfd(0, EFD_NONBLOCK);
	if (state.read_v3_startup_event_fd < 0)
	{
		perror("Failed to open v3 startup eventfd");
		return 1;
	}
	state.read_v3_run_event_fd = eventfd(0, EFD_NONBLOCK);
	if (state.read_v3_run_event_fd < 0)
	{
		perror("Failed to open v3 run eventfd");
		return 1;
	}
	else
	{
		DEBUG_PRINT("Opened read eventfd :-)\n");
	}
	state.read_v3_quit_event_fd = eventfd(0, EFD_NONBLOCK);
	if (state.read_v3_quit_event_fd < 0)
	{
		perror("Failed to open v3 quit eventfd");
		return 1;
	}
	state.read_v3_done_event_fd = eventfd(0, EFD_NONBLOCK);
	if (state.read_v3_done_event_fd < 0)
	{
		perror("Failed to open v3 done eventfd");
		return 1;
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
	state.read_args.output_fd = state.sock_data;
	state.read_v3_args.quit_event_fd = state.read_v3_quit_event_fd;
	state.read_v3_args.startup_event_fd = state.read_v3_startup_event_fd;
	state.read_v3_args.run_event_fd = state.read_v3_run_event_fd;
	state.read_v3_args.done_event_fd = state.read_v3_done_event_fd;
	state.read_v3_args.output_fd = state.sock_data;

	/* Prepare write args */
	state.write_args.quit_event_fd = state.write_thread_event_fd;
	state.write_args.input_fd = state.sock_data;

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

	/* Register control socket with epoll */
	epoll_event.events = EPOLLIN;
	epoll_event.data.ptr = handle_control;
	if (epoll_ctl(epoll_fd, EPOLL_CTL_ADD, state.sock_control, &epoll_event) < 0)
	{
		/* Failed to register control socket with epoll */
		perror("Failed to register control socket with epoll");
		return 1;
	}
	else
	{
		DEBUG_PRINT("Registered control socket with epoll :-)\n");
	}

	/* Worker lifecycle events keep slow IIO setup/teardown off control epoll. */
	epoll_event.events = EPOLLIN;
	epoll_event.data.ptr = handle_v3_startup_event;
	if (epoll_ctl(epoll_fd, EPOLL_CTL_ADD,
		state.read_v3_startup_event_fd, &epoll_event) < 0)
	{
		perror("Failed to register v3 startup eventfd");
		return 1;
	}
	epoll_event.data.ptr = handle_v3_done_event;
	if (epoll_ctl(epoll_fd, EPOLL_CTL_ADD,
		state.read_v3_done_event_fd, &epoll_event) < 0)
	{
		perror("Failed to register v3 done eventfd");
		return 1;
	}

	/* Here we go */
	printf("Ready :-)\n");

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

	/* Stop threads */
	stop_thread(&state, false);
	stop_v3_thread(&state);
	stop_thread(&state, true);

	/* Close files */
	close(epoll_fd);
	close(state.read_thread_event_fd);
	close(state.read_v3_startup_event_fd);
	close(state.read_v3_run_event_fd);
	close(state.read_v3_quit_event_fd);
	close(state.read_v3_done_event_fd);
	close(state.write_thread_event_fd);
	close(state.sock_control);
	close(state.sock_data);
	spf_time_anchor_reader_destroy(&state.time_anchor_reader);

	/* Goodbye */
	printf("Bye!\n");

	return 0;
}

static int handle_v3_startup_event(state_t *state)
{
	uint64_t result = 0;
	if (read(state->read_v3_startup_event_fd, &result, sizeof(result)) !=
		(ssize_t)sizeof(result))
		return errno == EAGAIN ? 0 : -1;
	if (!state->read_v3_started || result != 1 ||
		state->rx_lifecycle.state != SPF_IP_RX_STARTING)
	{
		state->rx_lifecycle.stale_event_count++;
		return 0;
	}
	if (!spf_ip_rx_lifecycle_ready(&state->rx_lifecycle) ||
		state->pending_start_slot < 0)
		return -1;
	DEBUG_PRINT("RX generation %llu stream %llu armed\n",
		(unsigned long long)state->rx_lifecycle.generation,
		(unsigned long long)state->rx_lifecycle.stream_id);
	const spf_ip_control_v1_t *request =
		&state->control_replay.entries[state->pending_start_slot].request;
	spf_ip_control_v1_t response;
	spf_ip_control_init_reply(&response, request,
		SPF_IP_CONTROL_STARTED, state->rx_lifecycle.stream_id);
	(void)prepare_and_send_control(state, state->pending_start_slot,
		&response, &state->pending_start_peer);
	return 0;
}

static int handle_v3_done_event(state_t *state)
{
	uint64_t result = 0;
	if (read(state->read_v3_done_event_fd, &result, sizeof(result)) !=
		(ssize_t)sizeof(result))
		return errno == EAGAIN ? 0 : -1;
	if (!state->read_v3_started)
	{
		state->rx_lifecycle.stale_event_count++;
		return 0;
	}
	const uint64_t stream_id = state->rx_lifecycle.stream_id;
	if (pthread_join(state->thread_read_v3, NULL) != 0)
		return -1;
	state->read_v3_started = false;
	state->read_v3_quit_signaled = false;
	state->v3_worker_done_count++;
	DEBUG_PRINT("RX generation %llu stream %llu worker done result=%llu\n",
		(unsigned long long)state->rx_lifecycle.generation,
		(unsigned long long)stream_id,
		(unsigned long long)result);
	if (!spf_ip_rx_lifecycle_worker_done(
		&state->rx_lifecycle, stream_id, result))
		return 0;
	(void)spf_ip_rx_lifecycle_reap(&state->rx_lifecycle);
	state->active_v3_stream_id = 0;

	if (state->pending_start_slot >= 0)
	{
		const int slot = state->pending_start_slot;
		const spf_ip_control_v1_t *request =
			&state->control_replay.entries[slot].request;
		spf_ip_control_v1_t response;
		spf_ip_control_init_error(&response, request->request_id,
			result == 3 ? -ECANCELED : -EIO);
		(void)prepare_and_send_control(
			state, slot, &response, &state->pending_start_peer);
	}
	if (state->pending_stop_slot >= 0)
	{
		const int slot = state->pending_stop_slot;
		const spf_ip_control_v1_t *request =
			&state->control_replay.entries[slot].request;
		spf_ip_control_v1_t response;
		if (result == 1 || result == 3)
			spf_ip_control_init_reply(&response, request,
				SPF_IP_CONTROL_STOPPED, stream_id);
		else
			spf_ip_control_init_error(
				&response, request->request_id, -EIO);
		(void)prepare_and_send_control(
			state, slot, &response, &state->pending_stop_peer);
	}
	return 0;
}

/* Private functions */
static int handle_control(state_t *state)
{
	socklen_t len;
	struct sockaddr_in addr;
	union
	{
		cmd_ip_t legacy;
		spf_ip_control_v1_t v3;
		spf_time_anchor_query_v1_t time_anchor;
	} command;
	int ret;

	/* Read datagram from socket */
    len = sizeof(addr);
    ret = recvfrom(state->sock_control,
		&command,
		sizeof(command),
		0,
		(struct sockaddr*)&addr,
		&len);
	if (ret < 0)
	{
		perror("Failed to read cmd from control socket");
		return -1;
	}
	const spf_ip_control_datagram_kind_t command_kind =
		spf_ip_control_datagram_classify(
			&command,
			(size_t)ret,
			SDR_IP_GADGET_MAGIC,
			sizeof(cmd_ip_header_t),
			SPF_TIME_ANCHOR_QUERY_MAGIC);
	if (command_kind == SPF_IP_CONTROL_DATAGRAM_DROP)
	{
		DEBUG_PRINT("Ignore malformed control datagram (%d bytes)\n", ret);
		return 0;
	}
	if (command_kind == SPF_IP_CONTROL_DATAGRAM_TIME_ANCHOR)
	{
		const uint64_t request_id =
			ret >= 16 ? command.time_anchor.request_id : 0;
		if (ret != (int)sizeof(command.time_anchor) ||
			!spf_time_anchor_query_validate(&command.time_anchor))
		{
			spf_ip_control_v1_t error;
			spf_ip_control_init_error(&error, request_id, -EINVAL);
			(void)send_v3_control(state, &error, &addr);
			return 0;
		}
		if (state->time_anchor_cache_valid &&
			same_control_peer(&addr, &state->time_anchor_cache_peer) &&
			memcmp(&command.time_anchor,
				&state->time_anchor_cache_query,
				sizeof(command.time_anchor)) == 0)
		{
			(void)sendto(state->sock_control,
				&state->time_anchor_cache_reply,
				sizeof(state->time_anchor_cache_reply),
				0,
				(const struct sockaddr *)&addr,
				sizeof(addr));
			return 0;
		}
		spf_time_anchor_v1_t anchor;
		if (!spf_time_anchor_capture(
			&state->time_anchor_reader, request_id, &anchor))
		{
			spf_ip_control_v1_t error;
			spf_ip_control_init_error(&error, request_id, -EIO);
			(void)send_v3_control(state, &error, &addr);
			return 0;
		}
		state->time_anchor_cache_valid = true;
		state->time_anchor_cache_peer = addr;
		state->time_anchor_cache_query = command.time_anchor;
		state->time_anchor_cache_reply = anchor;
		(void)sendto(state->sock_control,
			&anchor,
			sizeof(anchor),
			0,
			(const struct sockaddr *)&addr,
			sizeof(addr));
		return 0;
	}
	if (command_kind == SPF_IP_CONTROL_DATAGRAM_V3)
	{
		if (ret != (int)sizeof(command.v3))
		{
			spf_ip_control_v1_t error;
			const uint64_t request_id = ret >= 20
				? command.v3.request_id : 0;
			spf_ip_control_init_error(&error, request_id, -EMSGSIZE);
			(void)send_v3_control(state, &error, &addr);
			return 0;
		}
		return handle_v3_control(state, &command.v3, &addr);
	}
	cmd_ip_t cmd = command.legacy;

	/* Print event summary */
	DEBUG_PRINT("Handle control socket command: %s\n", cmd_name(cmd.hdr.cmd));

	/* Act on command */
	switch (cmd.hdr.cmd)
	{
		case SDR_IP_GADGET_COMMAND_START_TX:
		{
			/* Check request size */
			if (ret != sizeof(cmd_ip_tx_start_req_t))
			{
				printf("Bad TX start request, incorrect data size\n");
				break;
			}

			/* Ensure thread stopped */
			stop_thread(state, true);

			/* Prepare args */
			DEBUG_PRINT("Start TX with chans: %08X, timestamp: %s, buffsize: %u\n",
						cmd.start_tx.enabled_channels,
						cmd.start_tx.timestamping_enabled ? "enabled" : "disabled",
						(unsigned int)cmd.start_tx.buffer_size);
			state->write_args.iio_channels = cmd.start_tx.enabled_channels;
			state->write_args.timestamping_enabled = cmd.start_tx.timestamping_enabled;
			state->write_args.iio_buffer_size = cmd.start_tx.buffer_size;

			/* Start thread */
			start_thread(state, true);
			break;
		}
		case SDR_IP_GADGET_COMMAND_START_RX:
		{
			/* Check request size */
			if (ret != sizeof(cmd_ip_rx_start_req_t))
			{
				printf("Bad RX start request, incorrect data size\n");
				break;
			}

			/* Ensure thread stopped */
			stop_v3_thread(state);
			stop_thread(state, false);

			/* Prepare args */
			char addr_str[INET_ADDRSTRLEN];
			if (inet_ntop(AF_INET, &(addr.sin_addr), addr_str, INET_ADDRSTRLEN) == NULL) {
				perror("Error converting address to string");
				addr_str[0] = '\0';
			}
			DEBUG_PRINT("Start RX with chans: %08X, timestamp: %s, buffsize: %u, pktsize: %u, dest: %s:%u\n",
						cmd.start_rx.enabled_channels,
						cmd.start_rx.timestamping_enabled ? "enabled" : "disabled",
						(unsigned int)cmd.start_rx.buffer_size,
						(unsigned int)cmd.start_rx.packet_size,
						addr_str, ntohs(cmd.start_rx.data_port));
			state->read_args.addr.sin_family = AF_INET;
			state->read_args.addr.sin_addr = addr.sin_addr;
			state->read_args.addr.sin_port = htons(cmd.start_rx.data_port);
			state->read_args.iio_channels = cmd.start_rx.enabled_channels;
			state->read_args.timestamping_enabled = cmd.start_rx.timestamping_enabled;
			state->read_args.iio_buffer_size = cmd.start_rx.buffer_size;
			state->read_args.udp_packet_size = cmd.start_rx.packet_size;

			/* Start thread */
			start_thread(state, false);
			break;
		}
		case SDR_IP_GADGET_COMMAND_STOP_TX:
		case SDR_IP_GADGET_COMMAND_STOP_RX:
		{
			/* Decide on TX vs RX thread */
			bool tx = (SDR_IP_GADGET_COMMAND_STOP_TX == cmd.hdr.cmd);

			DEBUG_PRINT("Stop %s\n", tx ? "TX" : "RX");

			/* Stop thread */
			stop_thread(state, tx);
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

static bool same_control_peer(
	const struct sockaddr_in *left,
	const struct sockaddr_in *right)
{
	return left->sin_family == right->sin_family &&
		left->sin_port == right->sin_port &&
		left->sin_addr.s_addr == right->sin_addr.s_addr;
}

static int handle_v3_control(state_t *state,
	const spf_ip_control_v1_t *request,
	const struct sockaddr_in *peer)
{
	spf_ip_control_v1_t response;
	int replay_slot = -1;
	const spf_ip_control_v1_t *cached = NULL;
	const spf_ip_replay_lookup_t replay_result =
		spf_ip_control_replay_lookup(&state->control_replay,
			peer, request, &replay_slot, &cached);
	if (replay_result == SPF_IP_REPLAY_COLLISION)
	{
		spf_ip_control_init_error(&response, request->request_id, -EALREADY);
		(void)send_v3_control(state, &response, peer);
		return 0;
	}
	if (replay_result == SPF_IP_REPLAY_STALE)
	{
		spf_ip_control_init_error(&response, request->request_id, -ESTALE);
		(void)send_v3_control(state, &response, peer);
		return 0;
	}
	if (replay_result == SPF_IP_REPLAY_PENDING)
		return 0;
	if (replay_result == SPF_IP_REPLAY_PREPARED)
	{
		if (send_v3_control(state, cached, peer) &&
			spf_ip_control_replay_mark_responded(
				&state->control_replay, replay_slot))
			on_control_response_sent(state, replay_slot);
		return 0;
	}
	if (replay_result == SPF_IP_REPLAY_RESPONDED)
	{
		(void)send_v3_control(state, cached, peer);
		return 0;
	}

	if (!spf_ip_control_validate(request))
	{
		spf_ip_control_init_error(&response, request->request_id, -EINVAL);
		(void)cache_immediate_control(state, request, &response, peer);
		return 0;
	}
	if (request->message_type == SPF_IP_CONTROL_QUERY_CAPABILITIES)
	{
		spf_ip_control_init_capabilities(&response, request->request_id);
		if ((request->flags &
			SPF_IP_CONTROL_FLAG_QUERY_TRANSPORT_CAPABILITIES) != 0)
			response.flags |= SPF_IP_CONTROL_FLAG_BUFFERED_FINITE_RX |
				SPF_IP_CONTROL_FLAG_USB_CLASS_PACING;
		(void)cache_immediate_control(state, request, &response, peer);
		return 0;
	}
	if (request->message_type == SPF_IP_CONTROL_START_RX)
	{
		if (request->protocol_min != 3)
		{
			spf_ip_control_init_error(
				&response, request->request_id, -EPROTONOSUPPORT);
			(void)cache_immediate_control(state, request, &response, peer);
			return 0;
		}
		if (state->read_started ||
			spf_ip_rx_lifecycle_busy(&state->rx_lifecycle))
		{
			spf_ip_control_init_error(&response, request->request_id, -EBUSY);
			(void)cache_immediate_control(state, request, &response, peer);
			return 0;
		}
		if (!spf_ip_control_replay_begin(&state->control_replay,
			peer, request, &replay_slot))
		{
			spf_ip_control_init_error(&response, request->request_id, -ENOSPC);
			(void)send_v3_control(state, &response, peer);
			return 0;
		}
		uint64_t stream_id = state->next_stream_id++;
		if (stream_id == 0)
			stream_id = state->next_stream_id++;
		if (!spf_ip_rx_lifecycle_begin(&state->rx_lifecycle, stream_id))
		{
			spf_ip_control_init_error(&response, request->request_id, -EBUSY);
			(void)prepare_and_send_control(
				state, replay_slot, &response, peer);
			return 0;
		}
		state->pending_start_slot = replay_slot;
		state->pending_start_peer = *peer;
		reset_v3_eventfds(state);
		memset(&state->read_v3_args, 0, sizeof(state->read_v3_args));
		state->read_v3_args.quit_event_fd = state->read_v3_quit_event_fd;
		state->read_v3_args.startup_event_fd =
			state->read_v3_startup_event_fd;
		state->read_v3_args.run_event_fd = state->read_v3_run_event_fd;
		state->read_v3_args.done_event_fd = state->read_v3_done_event_fd;
		state->read_v3_args.output_fd = state->sock_data;
		state->read_v3_args.addr.sin_family = AF_INET;
		state->read_v3_args.addr.sin_addr = peer->sin_addr;
		state->read_v3_args.addr.sin_port = htons(request->data_port);
		state->read_v3_args.iio_channels = request->enabled_scan_mask;
		state->read_v3_args.samples_per_channel = request->samples_per_channel;
		state->read_v3_args.udp_datagram_bytes = request->max_datagram_bytes;
		state->read_v3_args.frame_count = request->frame_count;
		state->read_v3_args.stream_id = stream_id;
		state->read_v3_args.generation = state->rx_lifecycle.generation;
		state->read_v3_args.metadata_features = (uint32_t)request->features;
		state->read_v3_args.gain_observation_interval_samples =
			request->gain_observation_interval_samples;
		state->read_v3_args.gain_observation_capacity =
			request->gain_observation_capacity;
		state->read_v3_args.gain_event_capacity =
			request->gain_event_capacity;
		state->read_v3_args.target_payload_bytes_per_second =
			(request->flags & SPF_IP_CONTROL_FLAG_USB_CLASS_PACING) != 0
			? SPF_IP_DEFAULT_TX_PAYLOAD_BYTES_PER_SECOND
			: SPF_IP_LEGACY_TX_PAYLOAD_BYTES_PER_SECOND;
		state->read_v3_args.pacing_interval_us =
			SPF_IP_DEFAULT_PACING_INTERVAL_US;
		if (!launch_v3_thread(state))
		{
			(void)spf_ip_rx_lifecycle_worker_done(
				&state->rx_lifecycle, stream_id, 2);
			(void)spf_ip_rx_lifecycle_reap(&state->rx_lifecycle);
			spf_ip_control_init_error(&response, request->request_id, -EIO);
			(void)prepare_and_send_control(
				state, replay_slot, &response, peer);
			state->pending_start_slot = -1;
		}
		return 0;
	}
	if (request->message_type == SPF_IP_CONTROL_STOP_RX)
	{
		if (state->rx_lifecycle.state == SPF_IP_RX_IDLE &&
			request->stream_id == state->rx_lifecycle.completed_stream_id)
		{
			spf_ip_control_init_reply(&response,
				request, SPF_IP_CONTROL_STOPPED, request->stream_id);
			(void)cache_immediate_control(state, request, &response, peer);
			return 0;
		}
		if (request->stream_id != state->rx_lifecycle.stream_id)
		{
			spf_ip_control_init_error(&response, request->request_id, -ENOENT);
			(void)cache_immediate_control(state, request, &response, peer);
			return 0;
		}
		if (state->pending_stop_slot >= 0 ||
			state->rx_lifecycle.state == SPF_IP_RX_STOPPING)
		{
			spf_ip_control_init_error(&response, request->request_id, -EBUSY);
			(void)cache_immediate_control(state, request, &response, peer);
			return 0;
		}
		if (!spf_ip_control_replay_begin(&state->control_replay,
			peer, request, &replay_slot))
		{
			spf_ip_control_init_error(&response, request->request_id, -ENOSPC);
			(void)send_v3_control(state, &response, peer);
			return 0;
		}
		state->pending_stop_slot = replay_slot;
		state->pending_stop_peer = *peer;
		if (!request_v3_stop(state))
		{
			spf_ip_control_init_error(&response, request->request_id, -EIO);
			(void)prepare_and_send_control(
				state, replay_slot, &response, peer);
			state->pending_stop_slot = -1;
		}
		return 0;
	}
	spf_ip_control_init_error(&response, request->request_id, -EINVAL);
	(void)cache_immediate_control(state, request, &response, peer);
	return 0;
}

static bool prepare_and_send_control(state_t *state,
	int slot,
	const spf_ip_control_v1_t *response,
	const struct sockaddr_in *peer)
{
	if (!spf_ip_control_replay_prepare(
		&state->control_replay, slot, response))
		return false;
	if (!send_v3_control(state, response, peer))
		return false;
	if (!spf_ip_control_replay_mark_responded(
		&state->control_replay, slot))
		return false;
	on_control_response_sent(state, slot);
	return true;
}

static void on_control_response_sent(state_t *state, int slot)
{
	const spf_ip_control_v1_t *response =
		&state->control_replay.entries[slot].response;
	if (slot == state->pending_start_slot)
	{
		if (response->message_type == SPF_IP_CONTROL_STARTED &&
			state->rx_lifecycle.state == SPF_IP_RX_ARMED)
		{
			uint64_t release = 1;
			if (write(state->read_v3_run_event_fd,
				&release, sizeof(release)) == (ssize_t)sizeof(release) &&
				spf_ip_rx_lifecycle_started(&state->rx_lifecycle))
			{
				state->active_v3_stream_id = response->stream_id;
				state->v3_start_count++;
			}
			else
			{
				(void)request_v3_stop(state);
			}
		}
		state->pending_start_slot = -1;
	}
	if (slot == state->pending_stop_slot)
	{
		state->pending_stop_slot = -1;
		state->v3_stop_count++;
	}
}

static bool cache_immediate_control(state_t *state,
	const spf_ip_control_v1_t *request,
	const spf_ip_control_v1_t *response,
	const struct sockaddr_in *peer)
{
	int slot = -1;
	if (!spf_ip_control_replay_begin(
		&state->control_replay, peer, request, &slot))
		return send_v3_control(state, response, peer);
	return prepare_and_send_control(state, slot, response, peer);
}

static bool send_v3_control(state_t *state,
	const spf_ip_control_v1_t *response,
	const struct sockaddr_in *peer)
{
	const ssize_t sent = sendto(state->sock_control,
		response,
		sizeof(*response),
		0,
		(const struct sockaddr *)peer,
		sizeof(*peer));
	return sent == (ssize_t)sizeof(*response);
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

	/* Create appropriate thread */
	if (tx && !state->write_started)
	{
		/* Start thread */
		state->write_started = (0 == pthread_create(&state->thread_write, NULL, &THREAD_WRITE_Entrypoint, &state->write_args));
		if (!state->write_started)
		{
			perror("Failed to start write thread");
			return false;
		}
	}
	else if (!tx && !state->read_started)
	{
		/* Start thread */
		state->read_started = (0 == pthread_create(&state->thread_read, NULL, &THREAD_READ_Entrypoint, &state->read_args));
		if (!state->read_started)
		{
			perror("Failed to start read thread");
			return false;
		}
	}

	/* Return signal mask to old value, such that all signals will be handled by main thread */
	if (sigprocmask(SIG_SETMASK, &old_mask, NULL) < 0)
	{
		perror("Failed to unmask signals");
		return false;
	}

	return true;
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

		/* Join with thread */
		pthread_join(state->thread_write, NULL);

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

		/* Join with thread */
		pthread_join(state->thread_read, NULL);

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

static bool launch_v3_thread(state_t *state)
{
	if (state->read_v3_started)
		return false;
	sigset_t new_mask;
	sigset_t old_mask;
	sigfillset(&new_mask);
	if (sigprocmask(SIG_SETMASK, &new_mask, &old_mask) < 0)
		return false;
	state->read_v3_started = pthread_create(&state->thread_read_v3,
		NULL,
		&THREAD_READ_V3_Entrypoint,
		&state->read_v3_args) == 0;
	const bool mask_restored =
		sigprocmask(SIG_SETMASK, &old_mask, NULL) == 0;
	if (!state->read_v3_started || !mask_restored)
		return false;
	return true;
}

static bool request_v3_stop(state_t *state)
{
	if (!state->read_v3_started)
		return false;
	if (state->rx_lifecycle.state != SPF_IP_RX_STOPPING &&
		!spf_ip_rx_lifecycle_request_stop(&state->rx_lifecycle))
		return false;
	if (state->read_v3_quit_signaled)
		return true;
	const uint64_t value = 1;
	if (write(state->read_v3_quit_event_fd, &value, sizeof(value)) !=
		(ssize_t)sizeof(value))
		return false;
	state->read_v3_quit_signaled = true;
	return true;
}

static bool stop_v3_thread(state_t *state)
{
	if (!state->read_v3_started)
		return true;
	if (!request_v3_stop(state))
		return false;
	if (pthread_join(state->thread_read_v3, NULL) != 0)
		return false;
	state->read_v3_started = false;
	state->read_v3_quit_signaled = false;
	const uint64_t stream_id = state->rx_lifecycle.stream_id;
	(void)spf_ip_rx_lifecycle_worker_done(
		&state->rx_lifecycle, stream_id, 3);
	(void)spf_ip_rx_lifecycle_reap(&state->rx_lifecycle);
	state->active_v3_stream_id = 0;
	reset_v3_eventfds(state);
	return true;
}

static void reset_v3_eventfds(state_t *state)
{
	const int fds[] = {
		state->read_v3_startup_event_fd,
		state->read_v3_run_event_fd,
		state->read_v3_quit_event_fd,
		state->read_v3_done_event_fd,
	};
	for (size_t index = 0; index < ARRAY_SIZE(fds); ++index)
	{
		uint64_t value = 0;
		while (read(fds[index], &value, sizeof(value)) ==
			(ssize_t)sizeof(value))
			;
	}
	state->read_v3_quit_signaled = false;
}

static void signal_handler(int signum)
{
	(void)signum;

	/* Clear running flag */
	keep_running = 0;
}

static void print_usage(const char *program_name, FILE *dest)
{
	fprintf(dest, "Usage: %s [OPTIONS]\n", program_name);
	fprintf(dest, "OPTIONS:\n");
	fprintf(dest, "  -h, --help\tDisplay this help message\n");
	fprintf(dest, "  -d, --debug\tEnable debug output\n");
	fprintf(dest, "  -v, --version\tDisplay the version of the program\n");
}

static const char* cmd_name(uint32_t cmd)
{
	const char* name = "UNKNOWN";
	const char* cmd_names[] = {"START_TX", "START_RX", "STOP_TX", "STOP_RX"};

	if (cmd < ARRAY_SIZE(cmd_names))
	{
		name = cmd_names[cmd];
	}

	return name;
}
