#include "spf_ip_rx_lifecycle.h"

#include <stddef.h>
#include <string.h>

void spf_ip_rx_lifecycle_init(spf_ip_rx_lifecycle_t *lifecycle)
{
	if (lifecycle == NULL)
		return;
	memset(lifecycle, 0, sizeof(*lifecycle));
	lifecycle->state = SPF_IP_RX_IDLE;
}

bool spf_ip_rx_lifecycle_busy(const spf_ip_rx_lifecycle_t *lifecycle)
{
	return lifecycle == NULL || lifecycle->state != SPF_IP_RX_IDLE;
}

bool spf_ip_rx_lifecycle_allows_legacy_start(
	const spf_ip_rx_lifecycle_t *lifecycle,
	bool v3_worker_started)
{
	return !v3_worker_started && lifecycle != NULL &&
		lifecycle->state == SPF_IP_RX_IDLE;
}

bool spf_ip_rx_lifecycle_begin(spf_ip_rx_lifecycle_t *lifecycle,
	uint64_t stream_id)
{
	if (lifecycle == NULL || lifecycle->state != SPF_IP_RX_IDLE ||
		stream_id == 0)
		return false;
	lifecycle->generation++;
	if (lifecycle->generation == 0)
		lifecycle->generation++;
	lifecycle->stream_id = stream_id;
	lifecycle->worker_result = 0;
	lifecycle->state = SPF_IP_RX_STARTING;
	lifecycle->transition_count++;
	return true;
}

bool spf_ip_rx_lifecycle_ready(spf_ip_rx_lifecycle_t *lifecycle)
{
	if (lifecycle == NULL || lifecycle->state != SPF_IP_RX_STARTING)
		return false;
	lifecycle->state = SPF_IP_RX_ARMED;
	lifecycle->transition_count++;
	return true;
}

bool spf_ip_rx_lifecycle_started(spf_ip_rx_lifecycle_t *lifecycle)
{
	if (lifecycle == NULL || lifecycle->state != SPF_IP_RX_ARMED)
		return false;
	lifecycle->state = SPF_IP_RX_RUNNING;
	lifecycle->transition_count++;
	return true;
}

bool spf_ip_rx_lifecycle_request_stop(spf_ip_rx_lifecycle_t *lifecycle)
{
	if (lifecycle == NULL)
		return false;
	if (lifecycle->state == SPF_IP_RX_STOPPING)
	{
		lifecycle->duplicate_stop_count++;
		return false;
	}
	if (lifecycle->state != SPF_IP_RX_STARTING &&
		lifecycle->state != SPF_IP_RX_ARMED &&
		lifecycle->state != SPF_IP_RX_RUNNING)
		return false;
	lifecycle->state = SPF_IP_RX_STOPPING;
	lifecycle->transition_count++;
	return true;
}

bool spf_ip_rx_lifecycle_worker_done(spf_ip_rx_lifecycle_t *lifecycle,
	uint64_t stream_id,
	uint64_t worker_result)
{
	if (lifecycle == NULL || stream_id == 0 ||
		stream_id != lifecycle->stream_id ||
		(lifecycle->state != SPF_IP_RX_STARTING &&
		 lifecycle->state != SPF_IP_RX_ARMED &&
		 lifecycle->state != SPF_IP_RX_RUNNING &&
		 lifecycle->state != SPF_IP_RX_STOPPING))
	{
		if (lifecycle != NULL)
			lifecycle->stale_event_count++;
		return false;
	}
	lifecycle->worker_result = worker_result;
	lifecycle->completed_stream_id = stream_id;
	lifecycle->state = SPF_IP_RX_REAPABLE;
	lifecycle->transition_count++;
	return true;
}

bool spf_ip_rx_lifecycle_reap(spf_ip_rx_lifecycle_t *lifecycle)
{
	if (lifecycle == NULL || lifecycle->state != SPF_IP_RX_REAPABLE)
		return false;
	lifecycle->stream_id = 0;
	lifecycle->state = SPF_IP_RX_IDLE;
	lifecycle->transition_count++;
	return true;
}

void spf_ip_rx_lifecycle_fatal(spf_ip_rx_lifecycle_t *lifecycle)
{
	if (lifecycle == NULL)
		return;
	lifecycle->state = SPF_IP_RX_FATAL;
	lifecycle->transition_count++;
}

const char *spf_ip_rx_state_name(spf_ip_rx_state_t state)
{
	switch (state)
	{
		case SPF_IP_RX_IDLE: return "idle";
		case SPF_IP_RX_STARTING: return "starting";
		case SPF_IP_RX_ARMED: return "armed";
		case SPF_IP_RX_RUNNING: return "running";
		case SPF_IP_RX_STOPPING: return "stopping";
		case SPF_IP_RX_REAPABLE: return "reapable";
		case SPF_IP_RX_FATAL: return "fatal";
		default: return "unknown";
	}
}
