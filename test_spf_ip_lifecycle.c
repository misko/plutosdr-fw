#include "spf_ip_control_replay.h"
#include "spf_ip_rx_lifecycle.h"

#include <arpa/inet.h>
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <string.h>

static struct sockaddr_in peer(uint32_t address, uint16_t port)
{
	struct sockaddr_in value = {
		.sin_family = AF_INET,
		.sin_port = htons(port),
		.sin_addr.s_addr = htonl(address),
	};
	return value;
}

static spf_ip_control_v1_t request(uint64_t request_id,
	spf_ip_control_type_t type,
	uint64_t stream_id)
{
	spf_ip_control_v1_t value = {0};
	value.magic = SPF_IP_CONTROL_MAGIC;
	value.version = SPF_IP_CONTROL_VERSION;
	value.message_type = type;
	value.message_bytes = sizeof(value);
	value.request_id = request_id;
	value.stream_id = stream_id;
	return value;
}

static void test_clean_lifecycle(void)
{
	spf_ip_rx_lifecycle_t lifecycle;
	spf_ip_rx_lifecycle_init(&lifecycle);
	assert(lifecycle.state == SPF_IP_RX_IDLE);
	assert(!spf_ip_rx_lifecycle_busy(&lifecycle));
	assert(spf_ip_rx_lifecycle_allows_legacy_start(&lifecycle, false));
	assert(!spf_ip_rx_lifecycle_allows_legacy_start(&lifecycle, true));

	assert(spf_ip_rx_lifecycle_begin(&lifecycle, 41));
	assert(!spf_ip_rx_lifecycle_allows_legacy_start(&lifecycle, false));
	assert(lifecycle.state == SPF_IP_RX_STARTING);
	assert(lifecycle.generation == 1);
	assert(lifecycle.stream_id == 41);
	assert(!spf_ip_rx_lifecycle_begin(&lifecycle, 42));

	assert(spf_ip_rx_lifecycle_ready(&lifecycle));
	assert(lifecycle.state == SPF_IP_RX_ARMED);
	assert(spf_ip_rx_lifecycle_started(&lifecycle));
	assert(lifecycle.state == SPF_IP_RX_RUNNING);

	assert(spf_ip_rx_lifecycle_request_stop(&lifecycle));
	assert(lifecycle.state == SPF_IP_RX_STOPPING);
	assert(!spf_ip_rx_lifecycle_request_stop(&lifecycle));
	assert(spf_ip_rx_lifecycle_worker_done(&lifecycle, 41, 1));
	assert(lifecycle.state == SPF_IP_RX_REAPABLE);
	assert(lifecycle.worker_result == 1);
	assert(spf_ip_rx_lifecycle_reap(&lifecycle));
	assert(lifecycle.state == SPF_IP_RX_IDLE);
	assert(lifecycle.generation == 1);
	assert(lifecycle.stream_id == 0);
	assert(spf_ip_rx_lifecycle_allows_legacy_start(&lifecycle, false));
}

static void test_natural_completion_and_stale_event(void)
{
	spf_ip_rx_lifecycle_t lifecycle;
	spf_ip_rx_lifecycle_init(&lifecycle);
	assert(spf_ip_rx_lifecycle_begin(&lifecycle, 100));
	assert(spf_ip_rx_lifecycle_ready(&lifecycle));
	assert(spf_ip_rx_lifecycle_started(&lifecycle));
	assert(!spf_ip_rx_lifecycle_worker_done(&lifecycle, 99, 1));
	assert(lifecycle.state == SPF_IP_RX_RUNNING);
	assert(spf_ip_rx_lifecycle_worker_done(&lifecycle, 100, 1));
	assert(spf_ip_rx_lifecycle_reap(&lifecycle));
	assert(spf_ip_rx_lifecycle_begin(&lifecycle, 101));
	assert(lifecycle.generation == 2);
	assert(!spf_ip_rx_lifecycle_worker_done(&lifecycle, 100, 1));
	assert(lifecycle.state == SPF_IP_RX_STARTING);
}

static void test_start_failure_reaps_before_reuse(void)
{
	spf_ip_rx_lifecycle_t lifecycle;
	spf_ip_rx_lifecycle_init(&lifecycle);
	assert(spf_ip_rx_lifecycle_begin(&lifecycle, 55));
	assert(spf_ip_rx_lifecycle_worker_done(&lifecycle, 55, 2));
	assert(lifecycle.state == SPF_IP_RX_REAPABLE);
	assert(!spf_ip_rx_lifecycle_begin(&lifecycle, 56));
	assert(spf_ip_rx_lifecycle_reap(&lifecycle));
	assert(spf_ip_rx_lifecycle_begin(&lifecycle, 56));
}

static void test_replay_pending_prepared_and_response(void)
{
	spf_ip_control_replay_t replay;
	spf_ip_control_replay_init(&replay);
	const struct sockaddr_in client = peer(UINT32_C(0xc0a80164), 40000);
	spf_ip_control_v1_t start = request(10, SPF_IP_CONTROL_START_RX, 0);
	int slot = -1;
	const spf_ip_control_v1_t *cached = NULL;
	assert(spf_ip_control_replay_lookup(
		&replay, &client, &start, &slot, &cached) == SPF_IP_REPLAY_MISS);
	assert(spf_ip_control_replay_begin(&replay, &client, &start, &slot));
	assert(spf_ip_control_replay_lookup(
		&replay, &client, &start, NULL, NULL) == SPF_IP_REPLAY_PENDING);

	spf_ip_control_v1_t collision = start;
	collision.stream_id = 9;
	assert(spf_ip_control_replay_lookup(
		&replay, &client, &collision, NULL, NULL) ==
		SPF_IP_REPLAY_COLLISION);

	spf_ip_control_v1_t started = start;
	started.message_type = SPF_IP_CONTROL_STARTED;
	started.stream_id = 77;
	assert(spf_ip_control_replay_prepare(&replay, slot, &started));
	assert(spf_ip_control_replay_lookup(
		&replay, &client, &start, NULL, &cached) == SPF_IP_REPLAY_PREPARED);
	assert(cached != NULL && cached->stream_id == 77);
	assert(spf_ip_control_replay_mark_responded(&replay, slot));
	assert(spf_ip_control_replay_lookup(
		&replay, &client, &start, NULL, &cached) == SPF_IP_REPLAY_RESPONDED);
	assert(memcmp(cached, &started, sizeof(started)) == 0);
}

static void test_replay_is_peer_scoped_and_bounded(void)
{
	spf_ip_control_replay_t replay;
	spf_ip_control_replay_init(&replay);
	const struct sockaddr_in first = peer(UINT32_C(0xc0a80164), 40000);
	const struct sockaddr_in second = peer(UINT32_C(0xc0a80165), 40000);
	spf_ip_control_v1_t query = request(
		100, SPF_IP_CONTROL_QUERY_CAPABILITIES, 0);
	int slot = -1;
	assert(spf_ip_control_replay_begin(&replay, &first, &query, &slot));
	spf_ip_control_v1_t response = request(
		100, SPF_IP_CONTROL_CAPABILITIES, 0);
	assert(spf_ip_control_replay_prepare(&replay, slot, &response));
	assert(spf_ip_control_replay_mark_responded(&replay, slot));
	assert(spf_ip_control_replay_lookup(
		&replay, &second, &query, NULL, NULL) == SPF_IP_REPLAY_MISS);

	for (uint64_t id = 101;
		id < 101 + SPF_IP_CONTROL_REPLAY_CAPACITY;
		++id)
	{
		spf_ip_control_v1_t item = request(
			id, SPF_IP_CONTROL_QUERY_CAPABILITIES, 0);
		assert(spf_ip_control_replay_begin(&replay, &first, &item, &slot));
		spf_ip_control_v1_t item_response = request(
			id, SPF_IP_CONTROL_CAPABILITIES, 0);
		assert(spf_ip_control_replay_prepare(
			&replay, slot, &item_response));
		assert(spf_ip_control_replay_mark_responded(&replay, slot));
	}
	assert(spf_ip_control_replay_count(&replay) ==
		SPF_IP_CONTROL_REPLAY_CAPACITY);
	assert(spf_ip_control_replay_lookup(
		&replay, &first, &query, NULL, NULL) == SPF_IP_REPLAY_STALE);
}

static void test_evicted_side_effect_cannot_run_again(void)
{
	spf_ip_control_replay_t replay;
	spf_ip_control_replay_init(&replay);
	const struct sockaddr_in client = peer(UINT32_C(0xc0a80164), 40000);
	spf_ip_control_v1_t old_start = request(500, SPF_IP_CONTROL_START_RX, 0);
	int slot = -1;
	assert(spf_ip_control_replay_begin(&replay, &client, &old_start, &slot));
	spf_ip_control_v1_t started = request(500, SPF_IP_CONTROL_STARTED, 700);
	assert(spf_ip_control_replay_prepare(&replay, slot, &started));
	assert(spf_ip_control_replay_mark_responded(&replay, slot));
	for (uint64_t id = 501;
		id <= 500 + SPF_IP_CONTROL_REPLAY_CAPACITY; ++id)
	{
		spf_ip_control_v1_t item = request(
			id, SPF_IP_CONTROL_QUERY_CAPABILITIES, 0);
		assert(spf_ip_control_replay_begin(&replay, &client, &item, &slot));
		spf_ip_control_v1_t answer = request(
			id, SPF_IP_CONTROL_CAPABILITIES, 0);
		assert(spf_ip_control_replay_prepare(&replay, slot, &answer));
		assert(spf_ip_control_replay_mark_responded(&replay, slot));
	}
	assert(spf_ip_control_replay_lookup(
		&replay, &client, &old_start, NULL, NULL) == SPF_IP_REPLAY_STALE);
}

static void test_pending_entry_is_not_evicted(void)
{
	spf_ip_control_replay_t replay;
	spf_ip_control_replay_init(&replay);
	const struct sockaddr_in client = peer(UINT32_C(0xc0a80164), 40000);
	spf_ip_control_v1_t pending = request(1, SPF_IP_CONTROL_START_RX, 0);
	int pending_slot = -1;
	assert(spf_ip_control_replay_begin(
		&replay, &client, &pending, &pending_slot));
	for (uint64_t id = 2; id <= SPF_IP_CONTROL_REPLAY_CAPACITY; ++id)
	{
		spf_ip_control_v1_t item = request(
			id, SPF_IP_CONTROL_QUERY_CAPABILITIES, 0);
		int slot = -1;
		assert(spf_ip_control_replay_begin(&replay, &client, &item, &slot));
		spf_ip_control_v1_t response = request(
			id, SPF_IP_CONTROL_CAPABILITIES, 0);
		assert(spf_ip_control_replay_prepare(&replay, slot, &response));
		assert(spf_ip_control_replay_mark_responded(&replay, slot));
	}
	spf_ip_control_v1_t replacement = request(
		999, SPF_IP_CONTROL_QUERY_CAPABILITIES, 0);
	int replacement_slot = -1;
	assert(spf_ip_control_replay_begin(
		&replay, &client, &replacement, &replacement_slot));
	assert(replacement_slot != pending_slot);
	assert(spf_ip_control_replay_lookup(
		&replay, &client, &pending, NULL, NULL) == SPF_IP_REPLAY_PENDING);
}

int main(void)
{
	test_clean_lifecycle();
	test_natural_completion_and_stale_event();
	test_start_failure_reaps_before_reuse();
	test_replay_pending_prepared_and_response();
	test_replay_is_peer_scoped_and_bounded();
	test_evicted_side_effect_cannot_run_again();
	test_pending_entry_is_not_evicted();
	return 0;
}
