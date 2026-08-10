#ifndef SPF_IP_RX_LIFECYCLE_H
#define SPF_IP_RX_LIFECYCLE_H

#include <stdbool.h>
#include <stdint.h>

typedef enum
{
	SPF_IP_RX_IDLE = 0,
	SPF_IP_RX_STARTING,
	SPF_IP_RX_ARMED,
	SPF_IP_RX_RUNNING,
	SPF_IP_RX_STOPPING,
	SPF_IP_RX_REAPABLE,
	SPF_IP_RX_FATAL,
} spf_ip_rx_state_t;

typedef struct
{
	spf_ip_rx_state_t state;
	uint64_t generation;
	uint64_t stream_id;
	uint64_t completed_stream_id;
	uint64_t stale_event_count;
	uint64_t duplicate_stop_count;
	uint64_t transition_count;
	uint64_t worker_result;
} spf_ip_rx_lifecycle_t;

void spf_ip_rx_lifecycle_init(spf_ip_rx_lifecycle_t *lifecycle);
bool spf_ip_rx_lifecycle_busy(const spf_ip_rx_lifecycle_t *lifecycle);
bool spf_ip_rx_lifecycle_allows_legacy_start(
	const spf_ip_rx_lifecycle_t *lifecycle,
	bool v3_worker_started);
bool spf_ip_rx_lifecycle_begin(spf_ip_rx_lifecycle_t *lifecycle,
	uint64_t stream_id);
bool spf_ip_rx_lifecycle_ready(spf_ip_rx_lifecycle_t *lifecycle);
bool spf_ip_rx_lifecycle_started(spf_ip_rx_lifecycle_t *lifecycle);
bool spf_ip_rx_lifecycle_request_stop(spf_ip_rx_lifecycle_t *lifecycle);
bool spf_ip_rx_lifecycle_worker_done(spf_ip_rx_lifecycle_t *lifecycle,
	uint64_t stream_id,
	uint64_t worker_result);
bool spf_ip_rx_lifecycle_reap(spf_ip_rx_lifecycle_t *lifecycle);
void spf_ip_rx_lifecycle_fatal(spf_ip_rx_lifecycle_t *lifecycle);
const char *spf_ip_rx_state_name(spf_ip_rx_state_t state);

#endif
